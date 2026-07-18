# macOS Unzip Permissions Documentation Design

## Goal

Update `MAC_SETUP.md` so a user running the macOS default zsh can safely install SpeedyType after extracting the source release, including common file-permission and macOS privacy-permission conditions.

## Scope

This change is documentation-only. It does not change `scripts/setup_mac.sh`, the command wrapper, packaging, or runtime behavior.

## Documentation Design

The setup guide will use zsh as the default shell and will reference only `~/.zshrc` in the primary PATH instructions. The PATH update will be idempotent, take effect in the current terminal through `source ~/.zshrc`, and be verified with `command -v speedytype`.

The guide will explain that archive extraction can remove Unix executable bits. Before running setup, the user will either restore the setup script's owner execute permission with `chmod u+x scripts/setup_mac.sh` and invoke it directly, or run it explicitly through `bash scripts/setup_mac.sh`. The guide will verify that the installed `~/.local/bin/speedytype` wrapper is executable and recommend rerunning setup if it is not.

The guide will cover these permission-related edge cases:

- Keep the extracted project in a local, user-owned directory where the user can read, write, and traverse files.
- Move the project off a `noexec` external, network, or restricted volume if executable files still cannot run after `chmod`.
- Restrict a legacy or explicitly selected `.env` file to its owner with mode `600`; keyring remains the preferred secret store.
- Never use broad permissions such as `chmod -R 777`.
- If Gatekeeper blocks execution, verify the release source/checksum first and use macOS Privacy & Security controls instead of broadly removing quarantine attributes.

The guide will also identify the runtime permissions that macOS may request: Accessibility, Input Monitoring, and Microphone. It will note that these permissions may need to be granted again when a newly extracted release uses a different virtual-environment Python path.

## Verification

Review the rendered Markdown and check every command for zsh-compatible quoting and paths containing spaces. Confirm that the guide contains `~/.zshrc`, `source ~/.zshrc`, `chmod u+x`, wrapper verification, `.env` mode `600`, `noexec` guidance, all three macOS privacy permissions, and an explicit warning against `chmod -R 777`. Confirm that no setup or runtime source files changed.
