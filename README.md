# geospatial file measurement api

This is a FastAPI backend service that takes a geospatial file and returns measurements for the features inside it. You upload a KML, KMZ, GeoJSON, or a zip that contains a single shapefile, and the service reads every feature, stores it, and works out the area for polygons and the length for lines, while points are stored without a measurement. It is built with FastAPI, SQLAlchemy, SQLite, GeoPandas, Shapely, and pyproj, and always stores measurements in square metres and metres, converting to other units only when they are requested.

app/main.py - creates the FastAPI app, configures logging, initializes the database on startup, mounts the routes, and rejects a request whose body is already over the upload limit.

app/config.py - reads the environment settings once at startup: the data directory, the max upload size, the allowed file types, the CORS origins, and the log level.

app/database.py - builds the SQLAlchemy engine, provides the session each request uses, and turns on WAL mode with a busy timeout so concurrent uploads do not lock the SQLite database.

app/models.py - defines the two tables, one for uploaded files and one for the features inside them.

app/schemas.py - holds the pydantic models that shape the JSON responses and validate the area and length unit query parameters.

app/routes.py - contains the API endpoints for uploading, listing, fetching, deleting, measurements, summary, and features.

app/services.py - runs an upload from start to finish: saves the file, reads it, measures every feature, stores the results, computes the summary totals, and records a FAILED status with a reason when something goes wrong.

app/readers.py - opens a KML, KMZ, GeoJSON, or zipped shapefile into a GeoDataFrame and figures out the CRS, assuming EPSG:4326 when a shapefile has no .prj file.

app/measure.py - picks a projection centred on each feature, calculates the area of polygons or the length of lines, and converts between the allowed units.

app/edges.py - adds points along edges longer than 10 km before measuring, so the result does not depend on how many points a shape happens to have.

tests/conftest.py - provides the test client and the helpers that build sample KML and shapefile-zip uploads.

tests/test_measure.py - tests the measurement logic directly, comparing its output with independent geodesic values.

tests/test_api.py - tests the endpoints end to end with real uploads.

tests/test_units.py - tests the small internal functions one by one against values worked out by hand.

requirements.txt - lists the Python packages the app imports directly, with pinned versions.

constraints.txt - pins the exact version of every package that gets installed, including the ones that arrive through other packages.

pyproject.toml - holds the pytest and coverage settings, and the test run fails if coverage drops below 100 percent.

.github/workflows/tests.yml - installs the pinned packages on a clean Linux runner and runs the tests on every push.

Future scope: background processing with a job queue for very large files, support for more formats such as GeoPackage and PostGIS, and authentication with per-user files.
