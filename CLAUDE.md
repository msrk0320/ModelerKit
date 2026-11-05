# Modeler Kit

One-panel Blender 4.5+ add-on (`modelerkit/`) for the modeling team. Split from MadPlugin (`C:\Tools\MadPlugin`) but standalone: own `modelerkit.*` operator ids and `mk_*` scene settings. It deliberately shares the `_explode_*` object keys with MadPlugin, so don't rename them.

## Rules

- Never mention MadPlugin in user-facing text (README, panel labels, release notes, videos). The audience is the team's texturing artists.
- Match surrounding code: four-space indent, `snake_case`, short docstrings, comments only for the why.
- Every behavior change gets a focused test in `tests/` (`test_*_blender.py`, unittest, run inside Blender).
- Keep the README in step with the panel: every button and what it does.
- Client SKUs and assets never go in the repo.

## Tests

For each `tests\test_*_blender.py`:

```
blender -b --factory-startup --python-exit-code 1 --python <file>
```

Blender 4.5: `C:\Program Files\Blender Foundation\Blender 4.5\blender.exe`. Also run on 5.2 when the change touches Blender API calls. All must print `OK`.

Any scripted Blender run that installs an extension, adds a repository or changes preferences needs its own profile (`BLENDER_USER_RESOURCES=<temp dir>`), and `--factory-startup` for plain tests. A scripted run once wiped the real 4.5 preferences. Never write to the real config.

## Release (team gets it by auto-update)

The team's Blender reads `https://raw.githubusercontent.com/msrk0320/ModelerKit/master/dist/index.json`. The add-on adds this repository itself on first enable (`_add_update_repository` in `__init__.py`), with Check for Updates on Start on.

1. Bump `version` in `modelerkit/blender_manifest.toml` (semver: fix = patch, new button = minor). Blender only offers Update when the number is higher.
2. Run the tests above.
3. `python build.py`: builds `dist/modelerkit-<version>.zip`, moves older zips to `dist/old/` (ignored by git) and regenerates `dist/index.json`.
4. Commit source, `dist/index.json` and the new zip together, then push `master`. Commit message: `feat:`/`fix:` + `Modeler Kit <version> - <summary>`. Push only when the user asks.
5. The raw URL can lag a few minutes. Check it returns 200 for both the index and the zip.

Never change the repo URL or the id `modelerkit`: installed copies would stop updating. The repo is public; keep secrets out of it.

## Open

Nobody has clicked the panel in a live window; the auto-added repository timer, the Uninstall button inside a real extension install, and Ctrl+Z on Single Material from Root on 5.2 are only checked headless.
