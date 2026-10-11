---
name: reference-app-profile
description: "Extract a reference application's shipped metadata into a fixed profile — stack, requested permissions, signing and sandbox, integrations and endpoints, security policy, storage and update mechanism — with each claim labeled Confirmed, Inferred or Unknown. Metadata only: no decompilation or code tracing.\n\nTrigger: reference app, reference program, competitor app, app profile, what does this app use, permissions, entitlements, security headers, inspect app bundle, inspect APK"
---

# Reference Application Profile

## Use When
- The owner names a reference program and wants facts that are otherwise found only by trial and error:
  what it is built with, what it asks for, how it is signed and sandboxed, what it talks to and how it updates.
- A design decision needs those facts as input. Hand the profile to `mir-core:design` or `mir-core:spec-architect`.

Skip this skill for a complete open-source repository; read its source instead.

## Bounds
- No decompilation, disassembly or code tracing. Read only container listings, manifests, property lists,
  signatures, linked-library names, bundled package metadata and public response headers.
- Do not launch, install or log in to the target unless the owner asks; launching may raise OS permission
  prompts and side effects. Work on a copy in task scratch, never the installed original.
- Never bypass encryption, DRM, licensing or access controls. An encrypted or protected item is `Unknown`.
- Secrets, tokens and personal data found in metadata: report their presence and location, never their values.
- No active scanning of third-party servers: at most a few ordinary requests to public pages the owner named.
  Respect the target's terms of use.
- The profile informs the owner's own design. Do not copy the target's code or assets.

## Targets
Use what the host has; when a tool is missing, mark the dependent items `Unknown` with the missing tool
instead of installing software without the owner's approval.

- macOS application (`.app`, or `.dmg`/`.pkg` expanded to one): list `Contents/` (Frameworks, PlugIns,
  XPC services, helpers, `Resources/app.asar` for Electron); `plutil -p Contents/Info.plist` (bundle id,
  minimum OS, URL schemes, `NS*UsageDescription`, App Transport Security, update feed keys);
  `codesign -dv --verbose=4` and `codesign -d --entitlements -` (team, hardened runtime, sandbox and
  entitlements); `spctl -a -vv` (Gatekeeper and notarization); `otool -L` on the main executable.
- Electron or other JavaScript bundle: the bundled `package.json` (name, version, dependencies, update
  library); configuration files shipped beside it. Do not read or trace application source.
- Android APK: `unzip -l` (native library ABIs and names that identify a framework);
  `aapt dump badging` or `apkanalyzer manifest print` (SDK levels, permissions, exported components,
  intent filters, network security config); `apksigner verify --print-certs` (signing scheme, certificate).
- Web service: `curl -sI` on the pages the owner named (CSP, HSTS, frame and referrer policy, cookie flags,
  server and CDN hints); `robots.txt`, `/.well-known/security.txt` and other well-known files; framework
  markers in the returned HTML. Use a browser HAR only when the owner supplies one or asks for it.
- Other formats: list the container and its signing only; everything else is `Unknown`.

## Profile
Record each claim as one row: claim, status (`Confirmed` read directly from the artifact, `Inferred` from
indirect markers such as library names, or `Unknown`), and the command or path that produced it.
1. Target: name, version, platform, source of the copy, SHA-256 and inspection date.
2. Stack: languages, frameworks, runtimes and notable bundled libraries.
3. Permissions: requested permissions, usage descriptions and declared capabilities.
4. Signing and sandbox: signer, hardened runtime, sandbox, entitlements, notarization or signature scheme.
5. Integrations and endpoints: URL schemes, extensions, services, hosts and third-party SDKs.
6. Security policy: transport security, content security and cookie policy, exported components.
7. Storage: declared containers, databases, keychain or keystore use, cache locations.
8. Updates: update mechanism, feed or store, update library.
9. Unknowns: what could not be confirmed, why, and the smallest step that would confirm it.

## Report
Return the profile table, then the facts most relevant to the owner's design question, then the Unknowns.
Never upgrade an `Inferred` or `Unknown` row to `Confirmed` without its evidence.
