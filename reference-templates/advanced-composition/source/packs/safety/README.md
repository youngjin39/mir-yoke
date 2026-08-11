# Safety Pack

This stable, opt-in pack supplies a standard-library Python hook that normalizes changed paths,
blocks repository-bound secret and Git-internal paths, keeps shell checks narrow, and reports only
credential finding classes rather than matched values.

The example settings file is deliberately not installed as `.claude/settings.json`. A repository
owner must merge the hook entries into the repository's existing runtime configuration.
