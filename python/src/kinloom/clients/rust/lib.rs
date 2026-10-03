//! The Kinloom SDK as a crate: `kinloom.rs` is written to be dropped into a game as `mod kinloom;` (its macros name
//! `$crate::kinloom`), so the crate wraps it the same way and re-exports everything.
#[allow(clippy::all)]
pub mod kinloom;
pub use crate::kinloom::*;
