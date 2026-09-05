//! Milestone based progress; time alone never advances an installation.
use super::state::{Phase, Transaction};

pub fn received(transaction: &mut Transaction, bytes: u64) {
    transaction.downloaded = transaction.downloaded.saturating_add(bytes);
    let percent = if transaction.download_bytes == 0 {
        0.0
    } else {
        (transaction.downloaded as f64 / transaction.download_bytes as f64 * 85.0).min(85.0)
    };
    transaction.progress_percent = transaction.progress_percent.max(percent);
}

pub fn notify_available(phase: &Phase, installation_started: bool, confirmed_newer: bool) -> bool {
    confirmed_newer
        && !installation_started
        && !matches!(
            phase,
            Phase::Idle | Phase::Committed | Phase::RolledBack | Phase::Blocked
        )
}

pub fn validated_files(transaction: &mut Transaction, completed: usize, total: usize) {
    if total > 0 {
        transaction.progress_percent = transaction
            .progress_percent
            .max(85.0 + (completed.min(total) as f64 / total as f64 * 5.0));
    }
}
