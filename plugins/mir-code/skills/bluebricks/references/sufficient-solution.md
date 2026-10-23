# Stop at a sufficient solution

Inspired by DietrichGebert/ponytail at 09c434a.

Use beside the entrypoint's Ponytail ladder when choosing an implementation.
Stop at the first rung that satisfies the actual requirement:

1. Remove unnecessary work or satisfy the need with guidance.
2. Reuse existing project behavior.
3. Use built-ins or the standard library.
4. Prefer a justified, already-installed dependency over adding another package.
5. Prefer an immediately readable one-liner or adapter before custom code.
6. Write only the minimum custom implementation still needed.

A compressed expression that needs decoding is not an immediately readable solution.
A dependency's presence does not establish fitness, compatibility or permission.
The rung order matches Yoke's `.ai-harness/development-ai-rules.md:18-23`;
consumers follow their own repository rules rather than needing that file.

Do not simplify away security, data-loss protection, credential or privacy
safeguards, protected scope, compatibility, accessibility or explicit requirements.
A smaller diff is sufficient only when it preserves these obligations and the
required behavior. Do not substitute an undocumented shortcut for a requirement.
