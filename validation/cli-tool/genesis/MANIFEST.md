# Genesis - CLI File Organizer - Manifest

## Files created
- src/core.py (organize_files with symlink check + safe_destination)
- src/security.py (get_safe_path - path traversal guard)
- tests/test_core.py
- tests/test_security.py

## Tests written
- test_get_category_image: .jpg -> images
- test_get_category_unknown: .xyz -> other
- test_organize_moves_files: moves files to correct subfolders
- test_dry_run_does_not_move: dry-run leaves files in place
- test_symlink_is_skipped_not_followed: symlink NOT followed, real file NOT moved
- test_duplicate_filename_not_overwritten: photo.jpg + photo.jpg -> photo.jpg + photo_2.jpg
- test_safe_destination_increments_counter: counter suffix on collision
- test_valid_path_within_base_accepted: safe path passes validation
- test_path_traversal_raises: /etc input raises ValueError
- test_dotdot_traversal_raises: ../../ input raises ValueError
- test_sibling_dir_raises: sibling directory input raises ValueError

## Security measures included
- get_safe_path() validates all user-supplied directory arguments
- Symlink detection before any move operation
- No path traversal possible via directory argument or filenames

## Error handling included
- Symlinks skipped with reason in result["skipped"]
- Duplicate filenames get counter suffix (never overwrite)
- Path traversal raises ValueError before any filesystem op

## What Genesis added vs Claude Only
- src/security.py (entirely absent in Claude version)
- Symlink guard (absent in Claude version - would follow symlinks silently)
- safe_destination() (absent - Claude version silently overwrites)
- 7 additional tests: symlink, duplicate, path traversal (4 cases)
