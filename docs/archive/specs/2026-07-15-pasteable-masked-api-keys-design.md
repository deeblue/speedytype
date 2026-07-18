# Pasteable Masked API Keys Design

## Goal

Allow a first-time user to paste an API key directly into the Settings dialog
without clicking **Show** first, while keeping the key visually masked by
default.

## UI Behavior

Each `MaskedKeyField` continues to use a standard Qt `QLineEdit`, but the field
is always editable. Its default echo mode is `QLineEdit.EchoMode.Password`, so
typing, keyboard paste, and the native context-menu Paste action work while the
rendered value remains concealed.

The existing **Show / Hide** button changes only the echo mode:

- **Show** selects `QLineEdit.EchoMode.Normal`.
- **Hide** selects `QLineEdit.EchoMode.Password`.

Toggling visibility must not replace, truncate, or otherwise modify the field's
actual text. A newly opened field may contain an existing Keyring value or be
empty; both cases behave the same way.

## Data and Security Boundaries

`current_value()` reads the actual `QLineEdit` text. The existing Settings save
path remains responsible for writing changed values to Windows Credential
Manager or macOS Keychain through Keyring. Connection tests continue to use the
currently edited value.

This change does not add clipboard monitoring, a custom clipboard store, new
credential persistence, logging, or secret rendering in status messages.

## Testing

Automated Qt tests will verify:

- an initially empty key field is editable and password-masked;
- clipboard text can be pasted directly without revealing the field;
- `current_value()` receives the pasted key;
- Show / Hide changes only the echo mode and preserves the value;
- existing save, cancel, connection-test, and Keyring tests remain green.

The full project suite and source release build will be rerun after the change.

## Completion Criteria

- First-time key entry supports native paste without pressing **Show**.
- The pasted key stays visually masked until **Show** is selected.
- Visibility toggling never changes the stored field value.
- Keyring storage and all existing operational behavior remain unchanged.
