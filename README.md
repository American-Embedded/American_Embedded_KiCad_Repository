# American Embedded KiCad Repository

A custom KiCad Plugin and Content Manager (PCM) repository providing American Embedded color themes, libraries, and tools.

## Adding This Repository to KiCad

1. Open KiCad
2. Go to **Plugin and Content Manager**
3. Click **Manage Repositories**
4. Click **Add Repository** and enter:
   ```
   https://raw.githubusercontent.com/American-Embedded/American_Embedded_KiCad_Repository/main/repository.json
   ```
5. Click **OK** and refresh the package list

## Available Packages

### Color Themes

| Package | Description |
|---------|-------------|
| **American Embedded Dark** | Dark theme optimized for extended design sessions |
| **American Embedded Light** | Light theme for well-lit environments |

### Libraries

*Coming soon*

## Repository Structure

```
├── packages/
│   ├── themes/
│   │   ├── american-embedded-dark/
│   │   │   ├── colors/american-embedded-dark.json
│   │   │   ├── resources/icon.png
│   │   │   └── metadata.json
│   │   └── american-embedded-light/
│   │       └── ...
│   └── library/
│       └── american-embedded-library/
│           └── ...
├── scripts/
│   └── build_repository.py      # Packaging script
├── repository.json              # PCM repository index (auto-generated)
├── packages.json                # Package metadata (auto-generated)
└── resources.zip                # Package icons (auto-generated)
```

## How It Works

On every push to `main`:

1. GitHub Actions runs `scripts/build_repository.py`
2. Package ZIPs are created and uploaded to GitHub Releases
3. Metadata files (`repository.json`, `packages.json`, `resources.zip`) are committed to the repo
4. KiCad PCM automatically picks up updates via the stable raw GitHub URL

## Adding New Packages

### Color Theme

1. Create `packages/themes/<theme-name>/`
2. Add `colors/<theme-name>.json` (KiCad color theme file)
3. Add `resources/icon.png` (64x64 PNG)
4. Add `metadata.json`:
   ```json
   {
     "$schema": "https://go.kicad.org/pcm/schemas/v1",
     "name": "Theme Display Name",
     "description": "Short description (max 500 chars)",
     "description_full": "Long description",
     "identifier": "com.github.american-embedded.<unique-id>",
     "type": "colortheme",
     "author": {
       "name": "American Embedded",
       "contact": {
         "email": "build@amemb.com",
         "github": "https://github.com/American-Embedded"
       }
     },
     "license": "CC-BY-4.0",
     "resources": {
       "homepage": "https://github.com/American-Embedded/American_Embedded_KiCad_Repository"
     },
     "versions": [
       {
         "version": "1.0.0",
         "status": "stable",
         "kicad_version": "8.0"
       }
     ]
   }
   ```

### Library

1. Create `packages/library/<library-name>/`
2. Add content directories (at least one required):
   - `symbols/*.kicad_sym`
   - `footprints/*.pretty/`
   - `3dmodels/*.3dshapes/`
3. Add `resources/icon.png` (64x64 PNG)
4. Add `metadata.json` with `"type": "library"`

### Plugin

1. Create `packages/plugins/<plugin-name>/`
2. Add `plugins/__init__.py` and plugin code
3. Add `resources/icon.png` (64x64 PNG, toolbar icon 24x24)
4. Add `metadata.json` with `"type": "plugin"`

## Local Development

```bash
# Install dependencies
pip install jsonschema Pillow

# Build repository locally
python scripts/build_repository.py \
  --repo-root . \
  --output-dir output \
  --base-url "https://github.com/American-Embedded/American_Embedded_KiCad_Repository/releases/download/v1" \
  --metadata-url "https://raw.githubusercontent.com/American-Embedded/American_Embedded_KiCad_Repository/main" \
  --create-icons

# Output files will be in output/
```

## Supported Package Types

| Type | Description |
|------|-------------|
| `colortheme` | Color themes for KiCad editors |
| `library` | Symbol, footprint, and 3D model libraries |
| `plugin` | Python action plugins |
| `fab` | Fabrication service integrations |
| `datasource` | Component database connectors |

**Note:** Project templates are not supported by PCM and must be installed manually.

## License

- Color themes: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
- Libraries: [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
- Build scripts: [MIT](https://opensource.org/licenses/MIT)

## Contact

- GitHub: [American-Embedded](https://github.com/American-Embedded)
- Email: build@amemb.com
