# Claude Only - CLI File Organizer - Manifest

## Files created
- cli.py (Click entrypoint)
- core.py (organize_files logic)
- tests/test_core.py

## Tests written
- test_get_category_image: .jpg -> images
- test_get_category_unknown: .xyz -> other
- test_organize_moves_files: moves jpg and pdf to correct subfolders
- test_dry_run_does_not_move: dry-run leaves files in place

## Security measures included
- None

## Error handling included
- None - no path validation, no symlink check, no permission handling

## What is NOT present
- No path traversal guard (../../ input not validated)
- No symlink handling (symlinks treated as files, can be dangerous)
- No overwrite protection (duplicate filenames silently overwrite)
- No permission error handling
- No circular reference detection
