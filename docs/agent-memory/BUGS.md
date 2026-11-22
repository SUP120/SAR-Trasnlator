# Bugs and blockers

## B-001 · Local Earth Engine authorization [RESOLVED]

The owner completed local Google authorization. On 2026-11-21, `scripts/check_access.py` exited 0 and the North Guwahati live API job returned all layers and both reports.

## B-002 · Windows restricted execution blocks localhost connections

The default managed environment denied loopback HTTP and caused the test client's socket setup to stall. Running with local sockets enabled resolved this. Local developer instructions bind only to `127.0.0.1`.

## B-003 · Test dependency deprecation warning

Starlette 0.52.1's test client emits an AnyIO deprecation warning about the `BlockingPortal` import. Recheck when updating FastAPI and its test dependencies.

## B-004 · Live scene and raster request failures [RESOLVED]

The first authenticated API runs failed in three places. Earth Engine requires initialization before setting its transport deadline. It also serializes `system:index` as a feature ID, so scene metadata now carries an explicit `scene_index` property. Its projection parser rejects the EPSG:6933 authority code, so the adapter supplies the equivalent WKT1 in the composite and pixel grid. The live North Guwahati run succeeded after all three fixes. The backend suite has a regression test for each.
