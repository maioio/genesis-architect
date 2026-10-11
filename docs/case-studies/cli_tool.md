# Case Study: Python CLI Tool

## What was requested

```
genesis init a Python CLI for batch processing and resizing images
```

## What Genesis found

**Repos researched:** python-pillow/Pillow, libvips/pyvips, pallets/click, fastapi/typer, imageio/imageio (17 repos total)

**Top pitfalls from GitHub Issues:**

| Pitfall | Issue | Found in |
|---------|-------|----------|
| Business logic in Click callback - untestable | [click#2416](https://github.com/pallets/click/issues/2416) | 5/5 repos |
| Pillow opens arbitrary files via path traversal | [Pillow#6051](https://github.com/python-pillow/Pillow/issues/6051) | 4/5 repos |
| No memory limit causes OOM on large images | [Pillow#5077](https://github.com/python-pillow/Pillow/issues/5077) | 3/5 repos |
| Silent data loss when output dir is same as input | [imageio#863](https://github.com/imageio/imageio/issues/863) | 3/5 repos |
| Click 8.1.4 type stubs break mypy silently | [click#2558](https://github.com/pallets/click/issues/2558) | 4/5 repos |

## What was saved

- CLI callback is 3 lines: parse args, call `core.process()`, handle errors. All logic is in `core.py`.
- `Pillow.Image.MAX_IMAGE_PIXELS` set at startup - decompression bombs rejected before load
- Input and output paths checked at startup: if equal, prompt user to confirm or abort
- `get_safe_path()` wraps all file opens - no `../` escapes
- `click>=8.1.7` pinned in `pyproject.toml` with comment referencing issue

## What was built

```
image-batch/
├── src/image_batch/
│   ├── cli.py       # Click entry point - args only, delegates to core
│   ├── core.py      # All image logic: resize, format convert, batch walk
│   └── utils/
│       ├── security.py   # get_safe_path(), output_dir_check()
│       └── limits.py     # MAX_IMAGE_PIXELS cap, file size guard
├── tests/
│   ├── test_core.py         # Tests core directly - no subprocess needed
│   ├── test_security.py     # Path traversal, oversized image rejection
│   └── test_cli.py          # CliRunner integration tests
├── pyproject.toml   # click>=8.1.7 pinned, mypy strict
└── .github/workflows/ci.yml
```

**Time to first test run:** 2 minutes after scaffold
**Path traversal reports:** 0
**OOM incidents on large batch:** 0
**Tests that require subprocess:** 0 (core is fully testable in-process)
