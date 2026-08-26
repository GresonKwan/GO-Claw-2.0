use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum ClientPhase {
    ProcessStarting,
    BootstrapCreating,
    BootstrapReady,
    BackendReady,
    ConsoleNavigating,
    ConsoleReady,
    DesktopActive,
    BrowserFallback,
    FatalStartup,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum BrowserFallbackReason {
    ExplicitBrowserMode,
    WebviewBuildFailed,
    BootstrapReadyTimeout,
    ConsoleNavigationFailed,
    ConsoleReadyTimeout,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) enum FatalStartupReason {
    BackendStartupFailed,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ClientReadinessSnapshot {
    pub(crate) schema_version: u8,
    pub(crate) launch_id: u64,
    pub(crate) phase: ClientPhase,
    pub(crate) backend_port: Option<u16>,
    pub(crate) console_url: Option<String>,
    pub(crate) fallback_reason: Option<BrowserFallbackReason>,
    pub(crate) fatal_reason: Option<FatalStartupReason>,
    pub(crate) browser_opened: bool,
}

impl Default for ClientReadinessSnapshot {
    fn default() -> Self {
        Self {
            schema_version: 1,
            launch_id: 0,
            phase: ClientPhase::ProcessStarting,
            backend_port: None,
            console_url: None,
            fallback_reason: None,
            fatal_reason: None,
            browser_opened: false,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ReadinessErrorCode {
    StaleLaunch,
    InvalidPhase,
}

impl ReadinessErrorCode {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::StaleLaunch => "STALE_LAUNCH",
            Self::InvalidPhase => "INVALID_PHASE",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ReadinessError {
    pub(crate) code: ReadinessErrorCode,
    pub(crate) message: &'static str,
}

impl ReadinessError {
    fn stale_launch() -> Self {
        Self {
            code: ReadinessErrorCode::StaleLaunch,
            message: "client launch is no longer current",
        }
    }

    fn invalid_phase() -> Self {
        Self {
            code: ReadinessErrorCode::InvalidPhase,
            message: "client readiness transition is not valid in the current phase",
        }
    }
}

#[derive(Debug, Default)]
pub(crate) struct ReadinessMachine {
    snapshot: ClientReadinessSnapshot,
}

impl ReadinessMachine {
    pub(crate) fn snapshot(&self) -> ClientReadinessSnapshot {
        self.snapshot.clone()
    }

    pub(crate) fn begin_launch(&mut self) -> ClientReadinessSnapshot {
        let launch_id = self.snapshot.launch_id.saturating_add(1);
        self.snapshot = ClientReadinessSnapshot {
            launch_id,
            ..ClientReadinessSnapshot::default()
        };
        self.snapshot()
    }

    pub(crate) fn bootstrap_creating(
        &mut self,
        launch_id: u64,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[ClientPhase::ProcessStarting])?;
        self.snapshot.phase = ClientPhase::BootstrapCreating;
        Ok(self.snapshot())
    }

    pub(crate) fn bootstrap_ready(
        &mut self,
        launch_id: u64,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[ClientPhase::BootstrapCreating])?;
        self.snapshot.phase = if self.snapshot.backend_port.is_some() {
            ClientPhase::BackendReady
        } else {
            ClientPhase::BootstrapReady
        };
        Ok(self.snapshot())
    }

    pub(crate) fn backend_ready(
        &mut self,
        launch_id: u64,
        port: u16,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[
            ClientPhase::BootstrapCreating,
            ClientPhase::BootstrapReady,
            ClientPhase::BrowserFallback,
        ])?;
        self.snapshot.backend_port = Some(port);
        self.snapshot.console_url = Some(format!("http://127.0.0.1:{port}/console"));
        if self.snapshot.phase == ClientPhase::BootstrapReady {
            self.snapshot.phase = ClientPhase::BackendReady;
        }
        Ok(self.snapshot())
    }

    pub(crate) fn console_navigating(
        &mut self,
        launch_id: u64,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[ClientPhase::BackendReady])?;
        self.snapshot.phase = ClientPhase::ConsoleNavigating;
        Ok(self.snapshot())
    }

    pub(crate) fn console_ready(
        &mut self,
        launch_id: u64,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[ClientPhase::ConsoleNavigating])?;
        self.snapshot.phase = ClientPhase::ConsoleReady;
        Ok(self.snapshot())
    }

    pub(crate) fn desktop_active(
        &mut self,
        launch_id: u64,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[ClientPhase::ConsoleReady])?;
        self.snapshot.phase = ClientPhase::DesktopActive;
        Ok(self.snapshot())
    }

    pub(crate) fn fallback(
        &mut self,
        launch_id: u64,
        reason: BrowserFallbackReason,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        if self.snapshot.phase == ClientPhase::BrowserFallback {
            return Ok(self.snapshot());
        }
        let allowed = match self.snapshot.phase {
            ClientPhase::ProcessStarting => reason == BrowserFallbackReason::ExplicitBrowserMode,
            ClientPhase::BootstrapCreating
            | ClientPhase::BootstrapReady
            | ClientPhase::BackendReady
            | ClientPhase::ConsoleNavigating => true,
            _ => false,
        };
        if !allowed {
            return Err(ReadinessError::invalid_phase());
        }
        self.snapshot.phase = ClientPhase::BrowserFallback;
        self.snapshot.fallback_reason = Some(reason);
        Ok(self.snapshot())
    }

    pub(crate) fn backend_failed(
        &mut self,
        launch_id: u64,
    ) -> Result<ClientReadinessSnapshot, ReadinessError> {
        self.require_launch(launch_id)?;
        self.require_phase(&[
            ClientPhase::ProcessStarting,
            ClientPhase::BootstrapCreating,
            ClientPhase::BootstrapReady,
            ClientPhase::BrowserFallback,
        ])?;
        self.snapshot.phase = ClientPhase::FatalStartup;
        self.snapshot.fatal_reason = Some(FatalStartupReason::BackendStartupFailed);
        Ok(self.snapshot())
    }

    pub(crate) fn reserve_browser_open(&mut self, launch_id: u64) -> Result<bool, ReadinessError> {
        self.require_launch(launch_id)?;
        if self.snapshot.phase != ClientPhase::BrowserFallback
            || self.snapshot.backend_port.is_none()
            || self.snapshot.browser_opened
        {
            return Ok(false);
        }
        self.snapshot.browser_opened = true;
        Ok(true)
    }

    fn require_launch(&self, launch_id: u64) -> Result<(), ReadinessError> {
        if launch_id == self.snapshot.launch_id {
            Ok(())
        } else {
            Err(ReadinessError::stale_launch())
        }
    }

    fn require_phase(&self, phases: &[ClientPhase]) -> Result<(), ReadinessError> {
        if phases.contains(&self.snapshot.phase) {
            Ok(())
        } else {
            Err(ReadinessError::invalid_phase())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn machine_at_bootstrap() -> (ReadinessMachine, u64) {
        let mut machine = ReadinessMachine::default();
        let launch_id = machine.begin_launch().launch_id;
        machine.bootstrap_creating(launch_id).unwrap();
        (machine, launch_id)
    }

    #[test]
    fn happy_path_requires_console_readiness_before_desktop_activation() {
        let (mut machine, launch_id) = machine_at_bootstrap();

        machine.bootstrap_ready(launch_id).unwrap();
        machine.backend_ready(launch_id, 54321).unwrap();
        machine.console_navigating(launch_id).unwrap();
        machine.console_ready(launch_id).unwrap();
        let active = machine.desktop_active(launch_id).unwrap();

        assert_eq!(active.phase, ClientPhase::DesktopActive);
        assert_eq!(active.backend_port, Some(54321));
        assert_eq!(
            active.console_url.as_deref(),
            Some("http://127.0.0.1:54321/console")
        );
    }

    #[test]
    fn backend_may_be_ready_before_bootstrap() {
        let (mut machine, launch_id) = machine_at_bootstrap();

        let waiting = machine.backend_ready(launch_id, 54321).unwrap();
        assert_eq!(waiting.phase, ClientPhase::BootstrapCreating);
        assert_eq!(waiting.backend_port, Some(54321));

        let ready = machine.bootstrap_ready(launch_id).unwrap();
        assert_eq!(ready.phase, ClientPhase::BackendReady);
    }

    #[test]
    fn stale_launch_never_mutates_current_state() {
        let (mut machine, launch_id) = machine_at_bootstrap();
        let before = machine.snapshot();

        let error = machine.bootstrap_ready(launch_id + 1).unwrap_err();

        assert_eq!(error.code, ReadinessErrorCode::StaleLaunch);
        assert_eq!(machine.snapshot(), before);
    }

    #[test]
    fn invalid_transition_is_rejected() {
        let (mut machine, launch_id) = machine_at_bootstrap();

        let error = machine.console_ready(launch_id).unwrap_err();

        assert_eq!(error.code, ReadinessErrorCode::InvalidPhase);
        assert_eq!(machine.snapshot().phase, ClientPhase::BootstrapCreating);
    }

    #[test]
    fn fallback_is_terminal_but_late_backend_port_is_retained() {
        let (mut machine, launch_id) = machine_at_bootstrap();
        machine
            .fallback(launch_id, BrowserFallbackReason::WebviewBuildFailed)
            .unwrap();

        let fallback = machine.backend_ready(launch_id, 54321).unwrap();

        assert_eq!(fallback.phase, ClientPhase::BrowserFallback);
        assert_eq!(fallback.backend_port, Some(54321));
        assert_eq!(
            machine.console_navigating(launch_id).unwrap_err().code,
            ReadinessErrorCode::InvalidPhase
        );
    }

    #[test]
    fn browser_open_is_reserved_once_and_requires_a_ready_backend() {
        let (mut machine, launch_id) = machine_at_bootstrap();
        machine
            .fallback(launch_id, BrowserFallbackReason::ConsoleReadyTimeout)
            .unwrap();

        assert!(!machine.reserve_browser_open(launch_id).unwrap());
        machine.backend_ready(launch_id, 54321).unwrap();
        assert!(machine.reserve_browser_open(launch_id).unwrap());
        assert!(!machine.reserve_browser_open(launch_id).unwrap());
    }

    #[test]
    fn backend_failure_is_fatal_and_never_reserves_browser() {
        let (mut machine, launch_id) = machine_at_bootstrap();

        let fatal = machine.backend_failed(launch_id).unwrap();

        assert_eq!(fatal.phase, ClientPhase::FatalStartup);
        assert_eq!(
            fatal.fatal_reason,
            Some(FatalStartupReason::BackendStartupFailed)
        );
        assert!(!machine.reserve_browser_open(launch_id).unwrap());
    }

    #[test]
    fn backend_failure_upgrades_fallback_to_fatal() {
        let (mut machine, launch_id) = machine_at_bootstrap();
        machine
            .fallback(launch_id, BrowserFallbackReason::BootstrapReadyTimeout)
            .unwrap();

        let fatal = machine.backend_failed(launch_id).unwrap();

        assert_eq!(fatal.phase, ClientPhase::FatalStartup);
        assert_eq!(
            fatal.fallback_reason,
            Some(BrowserFallbackReason::BootstrapReadyTimeout)
        );
    }

    #[test]
    fn launch_ids_increase_within_the_process() {
        let mut machine = ReadinessMachine::default();
        let first = machine.begin_launch().launch_id;
        let second = machine.begin_launch().launch_id;

        assert_eq!(second, first + 1);
    }
}
