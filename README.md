# geo-careatlas
A service to host notebooks


# Installation

## 1. install uv  
follow the guide at https://github.com/UNDP-Data/geo-knowhow/blob/main/UV.md#installation


# Administration

## Restoring archived apps and notebooks

When an owner archives an app or a notebook, CareAtlas moves it into the
`_archive/` folder of the content repository
([geo-careatlas-notebooks](https://github.com/UNDP-Data/geo-careatlas-notebooks)).
The name records when it was archived:

| Archived item | Location |
|---|---|
| App | `_archive/<app>-<YYYYMMDD-HHMMSS>/` |
| Notebook | `_archive/<app>/<notebook>-<YYYYMMDD-HHMMSS>.py` |

After `ARCHIVE_RETENTION_DAYS` (30 by default) CareAtlas removes the item from
the repository, but it stays in the git history. For an archived app, it also
deletes what editors had for it: their copies on the server (including anything
they hadn't committed), their `edit/<app>/<user>` branches on GitHub and any
open review requests. This is skipped if a new app has taken the same name in
the meantime.

Restoring the app itself takes a clone of the content repository and write
access to it:

```bash
git clone https://github.com/UNDP-Data/geo-careatlas-notebooks.git
cd geo-careatlas-notebooks
```

**Within the retention period**, the item is still in `_archive/`. Move it back
and commit:

```bash
git mv _archive/<app>-<timestamp> <app>                              # an app
git mv _archive/<app>/<notebook>-<timestamp>.py <app>/<notebook>.py  # a notebook
git commit -m "Restore <app>"
git push
```

**After the retention period**, first bring it back from history:

```bash
# Find the commit that removed it
git log --diff-filter=D --format='%h %ci %s' -- '_archive/<app>*'

# Check it out from the commit before the removal, then move it back as above
git checkout <commit>~1 -- '_archive/<app>-<timestamp>'
git mv _archive/<app>-<timestamp> <app>
git commit -m "Restore <app>"
git push
```

CareAtlas picks up the change within five minutes. Before pushing, make sure no
app with the same name has been created since; otherwise restore it under a
different folder name.

