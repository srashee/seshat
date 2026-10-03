# Publish Seshat to GitHub

This repository can be added directly to Home Assistant's App Store after it is pushed to GitHub. `repository.yaml` and the `seshat/` app folder are already at the required locations. Initial installations build from source; publishing a container image is optional.

## First push

The configured remote is `git@github.com:srashee/seshat.git`. Create an empty public repository at `srashee/seshat` if it does not already exist, without generating another README, license, or gitignore. Then, in this project directory:

```bash
git push -u origin HEAD
```

The remote uses SSH. Your GitHub SSH key must be configured on this computer. No push has been performed during preparation. Inspect `git remote -v` to confirm the destination.

Open the repository's **Actions** tab after pushing. The Verify workflow runs lint, unit tests, real-model tests, Docker build and a container health check. Wait for it to succeed before installing on HAOS. Docker checks have not been completed on the development machine.

Repository, app, integration documentation and issue links are configured for `https://github.com/srashee/seshat`, with `@srashee` as the integration code owner.

## Add to Home Assistant

Go to **Settings → Apps → Install app → ⋮ → Repositories**, add `https://github.com/srashee/seshat`, and install **Seshat**. Use this HTTPS URL in Home Assistant, not the SSH Git remote. Older Home Assistant versions use the Add-ons/Add-on Store labels.

The App Store installs the recognition app only. Install the companion integration from `custom_components/seshat` as described in the README. This repository does not claim HACS/default-store validation.

## Versioned release

Update the app version, integration manifest version and changelog together. After the Verify workflow passes for the release commit:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The Release image workflow validates that both versions match the tag, runs tests, builds and publishes `ghcr.io/<owner>/seshat-amd64:1.0.0`, and creates a **draft GitHub release** with generated notes and `seshat-integration.zip`. Review the draft and publish it when ready.

Extract the integration ZIP into Home Assistant's `/config/custom_components/`; it contains the `seshat/` directory. Restart Core, then add Seshat under Devices & services. The ZIP excludes Python caches and contains no enrollment records.

GitHub Actions uses the built-in `GITHUB_TOKEN`; no personal token or repository secret needs to be committed. Ensure repository/organization policies allow Actions to publish packages and releases. If using the image outside your account, make its GHCR package public. To switch Home Assistant from source builds to published images, add `image: ghcr.io/<owner>/seshat-{arch}` to the app config only after the corresponding public version exists.

## Files intentionally excluded

Virtual environments, local environment secrets, runtime databases, model downloads, test caches, logs, build output and Node dependencies are ignored. `.env.example` contains no key and is included. Model acquisition remains checksum-verified during the build. The public-domain test image is intentionally included with its source attribution.
