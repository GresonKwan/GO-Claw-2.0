//! Component updater: pure contracts shared by the standalone engine and shell.
//! No application state, credentials or mutable data belong to a program slot.
pub mod bootstrap;
pub mod download;
pub mod extract;
pub mod manifest;
#[cfg(windows)]
pub mod native;
pub mod paths;
pub mod planner;
pub mod progress;
pub mod recovery;
pub mod slots;
pub mod staging;
pub mod state;
pub mod verify;

pub type Result<T> = std::result::Result<T, String>;
