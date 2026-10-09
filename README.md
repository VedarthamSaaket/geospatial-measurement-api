geospatial file measurement api

this is a backend service that takes a geospatial file and gives back measurements for the features inside it.
you upload a kml, kmz or geojson file, or a zip that has a shapefile in it.
the service reads every feature, stores it, and works out the area for polygons and the length for lines.
points are stored but they dont get a measurement.
it is built with fastapi, sqlalchemy, sqlite, geopandas, shapely and pyproj.


what each file does

app/main.py creates the fastapi app, sets up logging and the database on startup, plugs in the routes and rejects a body that is too big.
app/config.py holds the settings like where data is stored, the max upload size and the allowed file types.
app/database.py creates the sqlalchemy engine and the session that each request uses, and sets the sqlite options.
app/models.py has the two tables, one for uploaded files and one for the features inside them.
app/schemas.py has the pydantic models that shape the json responses.
app/routes.py has the api endpoints.
app/services.py handles an upload from start to finish, it saves the file, reads it, measures every feature and stores the result, and it also works out the totals for the summary.
app/readers.py reads a kml, kmz, geojson or zipped shapefile into a geodataframe and figures out the crs.
app/measure.py has the measurement logic, it picks a projection for each feature and calculates area or length, and it converts units.
app/edges.py adds points along long edges before measuring, so the result does not depend on how many points a shape has.
tests/conftest.py has the test client and helpers that build sample kml and shapefile zips.
tests/test_measure.py tests the measurement logic directly.
tests/test_api.py tests the endpoints with real uploads.
tests/test_units.py tests the small internal functions one by one against values worked out by hand.
requirements.txt lists the python packages the app uses directly.
constraints.txt has the exact version of every package that gets installed, including the ones that come in through other packages.
pyproject.toml has the pytest and coverage settings.
.github/workflows/tests.yml runs the tests on github for every push.
Dockerfile builds an image that runs the app the same way on any machine.


setup

you need python 3.11 or newer.

```
git clone <repo url>
cd geospatial-measurement-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -c constraints.txt
uvicorn app.main:app --reload
```

the api runs on http://localhost:8000 and the interactive docs are on http://localhost:8000/docs.
a data folder is created on first run and it holds the sqlite database.
you can change the location with the DATA_DIR env variable, and the upload limit with MAX_UPLOAD_MB, the default is 50.
CORS_ORIGINS is the list of web origins that can call the api from a browser, separated by commas, and the default is * which means any.
LOG_LEVEL sets how much is logged, the default is INFO.
these settings are read once when the app starts, so the app has to be restarted after changing one.

to run the tests

```
python -m pytest
```

the test run also measures coverage and fails if any line or branch of the app code is not run.

to run it with docker instead

```
docker build -t geo-api .
docker run -p 8000:8000 -v geo-data:/srv/data geo-api
```


api

every path below works with or without the slash at the end.
opening http://localhost:8000/ sends you to the docs page.

POST /api/files/
uploads and processes a file.
it is a multipart form upload and the field name is file.
it accepts a .kml, .kmz or .geojson file, or a .zip that contains exactly one shapefile with its .shp, .shx and .dbf parts.

```
curl -X POST http://localhost:8000/api/files/ -F "file=@survey.kml"
```

```
{
  "id": "01fee8eece33463d9c3b9da6d57ec8d1",
  "filename": "survey.kml",
  "file_type": "kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "crs_assumed": false,
  "status": "COMPLETED",
  "error": null,
  "created_at": "2026-10-08T05:00:11.080537Z"
}
```

it returns 201 when the file was processed.
it returns 415 if the extension is not one of those, 400 if the file is empty and 413 if it is bigger than the limit.
if the content length of the request already says it is over the limit, the 413 comes back before the body is read.
it returns 400 if more than one file is sent in the same upload, and nothing is stored.
it returns 422 if the file has the right extension but cant be read or cant be processed, and the body has status FAILED with the reason.

```
{
  "id": "b8ced6ba54d44f16927a38c2a2c28c72",
  "filename": "broken.zip",
  "file_type": "zip",
  "feature_count": 0,
  "crs": null,
  "crs_assumed": false,
  "status": "FAILED",
  "error": "zip is missing shapefile parts: .dbf",
  "created_at": "2026-10-08T05:00:11.123366Z"
}
```

GET /api/files/
lists the uploaded files, newest first.
it takes limit and offset query params, limit is 100 by default and 1000 at most.
the response has total, limit, offset and a files list, and each item is the same shape as the upload response.

```
curl http://localhost:8000/api/files/
```

GET /api/files/{id}/
returns information about an uploaded file.
the response is the same shape as the upload response above.
it returns 404 if the id does not exist.

```
curl http://localhost:8000/api/files/01fee8eece33463d9c3b9da6d57ec8d1/
```

DELETE /api/files/{id}/
deletes a file and all of its features.
it returns 204 with no body, and 404 if the id does not exist.

```
curl -X DELETE http://localhost:8000/api/files/01fee8eece33463d9c3b9da6d57ec8d1/
```

GET /api/files/{id}/measurements/
returns the measurement for every feature in the file.
it takes limit and offset query params, limit is 100 by default and 1000 at most.
it also takes area_unit and length_unit.
area_unit can be square_metre, hectare, square_kilometre or acre, and the default is square_metre.
length_unit can be metre, kilometre, mile or foot, and the default is metre.
a unit that is not in the list returns 422.

```
curl http://localhost:8000/api/files/01fee8eece33463d9c3b9da6d57ec8d1/measurements/
```

```
{
  "file_id": "01fee8eece33463d9c3b9da6d57ec8d1",
  "total": 3,
  "limit": 100,
  "offset": 0,
  "measurements": [
    {
      "index": 0,
      "geometry_type": "Polygon",
      "measurement_type": "area",
      "value": 1176082.9673578592,
      "unit": "square_metre",
      "measurement_crs": "+proj=laea +lat_0=17.385 +lon_0=78.475 +datum=WGS84 +units=m",
      "note": null
    },
    {
      "index": 1,
      "geometry_type": "LineString",
      "measurement_type": "length",
      "value": 1534.3104335968108,
      "unit": "metre",
      "measurement_crs": "+proj=aeqd +lat_0=17.385 +lon_0=78.475 +datum=WGS84 +units=m",
      "note": null
    },
    {
      "index": 2,
      "geometry_type": "Point",
      "measurement_type": null,
      "value": null,
      "unit": null,
      "measurement_crs": null,
      "note": "no measurement for point geometry"
    }
  ]
}
```

GET /api/files/{id}/summary/
returns the totals for a file, so the client does not have to page through every measurement to add them up.
it takes the same area_unit and length_unit params.
measured_count is the number of features that got a measurement.

```
curl "http://localhost:8000/api/files/01fee8eece33463d9c3b9da6d57ec8d1/summary/?area_unit=hectare&length_unit=kilometre"
```

```
{
  "file_id": "01fee8eece33463d9c3b9da6d57ec8d1",
  "feature_count": 3,
  "measured_count": 2,
  "geometry_types": {"LineString": 1, "Point": 1, "Polygon": 1},
  "total_area": 117.60829673578593,
  "area_unit": "hectare",
  "total_length": 1.5343104335968107,
  "length_unit": "kilometre"
}
```

GET /api/files/{id}/features/
returns the stored features with their index, geometry type, geometry, crs and properties.
the geometry is in the crs of the file, and that crs is on every feature.
this one is not in the minimum requirements, i added it because the features are extracted anyway and there was no way to see them.
it takes the same limit and offset params.

```
curl "http://localhost:8000/api/files/01fee8eece33463d9c3b9da6d57ec8d1/features/?limit=1"
```

```
{
  "file_id": "01fee8eece33463d9c3b9da6d57ec8d1",
  "crs": "EPSG:4326",
  "total": 3,
  "limit": 1,
  "offset": 0,
  "features": [
    {
      "index": 0,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[78.47, 17.38, 0.0], [78.48, 17.38, 0.0], [78.48, 17.39, 0.0], [78.47, 17.39, 0.0], [78.47, 17.38, 0.0]]]
      },
      "crs": "EPSG:4326",
      "properties": {"Name": "plot a", "tessellate": -1, "extrude": 0, "visibility": -1}
    }
  ]
}
```


architecture

application structure
the app is split into small layers and each one only talks to the one below it.
routes.py only deals with http, it reads the request and turns results into responses.
services.py runs the upload flow and is the only place that ties reading, measuring and saving together.
readers.py and measure.py dont know anything about http or the database, they just take data in and give data back.
models.py and database.py are the storage layer.
this is why the measurement logic can be tested without starting the api.

file processing flow
the content length of the request is checked before anything is read, and a body over the limit is rejected there.
then the extension is checked.
the file is written to disk in 1 MB chunks and rejected if it goes over the size limit.
a kml is opened layer by layer, because every folder in a kml is a separate layer, and the layers are joined into one table.
a zip is checked to make sure it has exactly one .shp and its .shx and .dbf, then it is read straight from the zip without extracting it.
a kmz is a zip with a kml inside, so the kml is found, doc.kml first if it is there, and read from inside the archive the same way.
a geojson is read directly.
the crs is taken from the file.
each feature gets an index, its geometry type, its geometry as geojson, its properties and its measurement.
the features are inserted 1000 at a time, and the file row and all of its features are still one transaction, so a file is never half saved.
the uploaded file is deleted from disk after that because everything needed is in the database.
if the file cant be read, the file record is still saved with status FAILED and the reason.
if anything else breaks after the file was read, the record is also saved as FAILED, with the reason file could not be processed, and the real error goes to the log.
the reason never has the server folder in it, the path is cut out of the error before it is saved.
a kml or geojson that is valid but has no features is COMPLETED with a feature count of 0.

measurement calculation flow
a feature with no geometry gets no measurement and a note saying so.
points and multipoints get no measurement.
any other type that is not a polygon or a line, like a geometry collection, gets no measurement and a note, it does not crash the upload.
the z value is dropped because area and length are measured on the ground.
before measuring, extra points are added along every edge longer than 10 km.
if the file crs is in lon lat the points follow the geodesic, the shortest path on the earth between the two ends.
if the file crs is projected the points follow the straight line in that crs.
edges shorter than 10 km are left alone, so normal files are measured exactly like before.
the geometry is converted to lon lat first.
if a coordinate is not a number or the latitude is outside -90 to 90, the feature gets no measurement and a note, the rest of the file is still measured.
a polygon is then converted to a projection made for that feature and shapely calculates the area.
if the projected polygon is invalid, like a bowtie shape, it is repaired and a note is added.
this check is done after projecting, because a shape across the 180 degree line looks broken in lon lat when it is really fine.
multipolygons work the same way, the parts are added up, and holes are subtracted.
a line is measured in sections.
if any point of the line is more than 50 km from the centre of its projection, the line is cut in half and each half gets its own projection, and this repeats until the sections are small enough.
a section with only two points is projected from its first point, because distances from the centre are exact in that projection.
the parts of a multiline are measured one by one and added up.
area is stored in square metres and length in metres.
other units are worked out from those when the measurements or the summary are requested.

crs handling
nothing is ever measured in degrees.
every geometry is first converted from the file crs to EPSG:4326, even if the file was already in a projected crs.
i do this because a projected crs is not always good for measuring, web mercator for example makes areas much bigger than they are.
then for each feature i build a projection centred on the middle of that feature.
for polygons it is a lambert azimuthal equal area projection, which keeps area correct.
for lines it is an azimuthal equidistant projection, which keeps distances correct close to its centre.
the projection that was used is returned in measurement_crs so the result can be checked.
for a line that was measured in sections, measurement_crs is the projection centred on the whole line and the note says that sections were used.
if a feature is more than 180 degrees wide in lon lat, it is treated as crossing the 180 degree line, and the centre is worked out with the longitudes moved to 0 to 360 first.
without this the centre of a feature near 179 and -179 lands on the other side of the earth and the numbers come out wrong.
kml and kmz are always EPSG:4326 by their spec.
geojson is EPSG:4326 too unless the file has its own crs member, and then that one is used.
if a shapefile has no .prj file and all the coordinates fit inside lon lat ranges, i assume EPSG:4326 and set crs_assumed to true.
if it has no .prj and the coordinates dont look like lon lat, the features are stored but not measured, because guessing would give wrong numbers.
the stored geometry stays in the original crs of the file, only the measurement uses the projected version.


design decisions

fastapi instead of django
the service has seven endpoints and no admin, auth or templates, so django would be mostly unused.
fastapi also gives request validation and the /docs page for free.
django with drf would make more sense if this grew into a bigger app with users and permissions.

sqlite with sqlalchemy
sqlite needs no setup so anyone can clone and run it.
sqlalchemy is used so moving to postgres later is a change of the DATABASE_URL and not a rewrite.
i thought about postgres with postgis but the service does no spatial queries, it only stores and returns features, so geometry is kept as geojson in a json column.

geopandas with pyogrio for reading
shapefile, kml, kmz and geojson are all read by the same library, so there is one code path after the file is opened.
the pyogrio wheels come with gdal inside them, so pip install is enough and gdal does not have to be installed on the system.
the other option was fiona or gdal directly, which is harder to install and needs more code.

projection centred on each feature instead of utm
this was the main decision.
the usual answer is to pick the utm zone for the data and measure there, and that is what i tried first.
when i compared it with geodesic values from pyproj, utm was off by about 0.1 percent for area and 0.05 percent for length, because utm has a scale factor and gets worse near the edge of a zone.
it also needs special handling for features that cross two zones and for the poles.
a projection centred on the feature itself matched the geodesic values to less than 0.001 percent in the same tests, and it works anywhere without picking zones.
web mercator was not an option, it was about 10 percent off for area at 17 degrees latitude and it gets much worse further from the equator.
i also considered skipping projection and using geodesic area on the ellipsoid directly, but the assignment asks to transform to a projected crs before measuring.
one projection per file would be faster, but a file can cover a whole country and then features far from the centre get distorted.

measuring lines in sections
an azimuthal equidistant projection is only exact for distances from its centre, so it gets worse as a line gets longer.
with one projection for the whole line, a 13000 km long line was 0.5 percent off and a multiline with two parts on different continents was 4.6 percent off.
with sections every case i tested matched the geodesic length to better than 0.001 percent, and short lines are still measured in one projection like before.
polygons dont need this, lambert azimuthal equal area keeps area correct everywhere and not only at the centre.

checking validity after projecting
at first i repaired invalid polygons in the file crs before projecting.
a circle drawn across the 180 degree line then got repaired into the wrong shape, because in lon lat its points jump from 180 to -180.
in the projected plane it is a normal circle, so that is where the check is done now.

paths with and without the slash
the assignment writes the paths with a slash at the end, so those are the real routes.
fastapi answers a path without the slash with a 307 redirect, and a client that does not follow redirects just sees an empty response, and an upload gets sent twice.
so a small middleware adds the slash before routing, and both forms give the same answer with no redirect.

processing inside the upload request
the file is processed while the request is open and the response comes back with the final status.
this keeps the service to one process with nothing else to run.
the endpoint is a normal def function so fastapi runs it in a thread pool and it does not block other requests.
the other option was a background worker with celery or similar, which is better for very big files but adds a broker and a worker for an assignment that doesnt need it.
the status field is already stored, so moving to background processing later would not change the api.

reading the shapefile straight from the zip
gdal can read inside a zip, so the archive is never extracted.
this avoids the zip slip problem where a bad archive writes files outside the target folder.
the zip is still checked first so the error says exactly which part is missing.

one bad feature does not fail the file
a feature that cant be measured gets a null value and a note explaining why.
this covers missing geometry, unsupported types, coordinates outside the valid range and anything else that goes wrong while measuring.
the client still gets every other feature.
only a file that cant be opened at all is marked FAILED.

failed uploads are saved
an unreadable file returns 422 but the record is kept with the error, so GET /api/files/{id}/ can show what went wrong later.
at first only read errors were handled this way, and an error in a later step came back as a 500 with nothing saved.
now every step after the upload is covered, so the rule is the same no matter where it breaks.
for an error i did not expect, the client only gets a fixed message, because the real text could have server paths or library details in it.

logging
a feature that cant be measured only gets a note, and a file that fails only gets a short reason, so without a log a real bug would look the same as a bad file.
the full error with its traceback is logged, together with the file id, so a FAILED record can be matched to its log line.
a line is also logged for every file that was processed, with the number of features.
i used the logging module from python and not a logging package, the service is small and this needs nothing installed.

checking the size before reading the body
the size limit used to be checked only while the file was written to disk.
by then the server had already received the whole body, so a 5 GB upload was fully taken in just to be rejected.
now a middleware looks at the content length header first and answers 413 without reading anything.
i first put this check in a fastapi dependency, and a test showed that fastapi reads the form before it runs dependencies, so it had to be a middleware.
the limit while writing is still there, because a client can send a body with no content length or a wrong one.
the header check allows 64 KB on top of the limit for the multipart form around the file.
the cors middleware is added last so it wraps this one, and a browser page still gets a readable 413.

sqlite in wal mode with a busy timeout
uploads run in a thread pool, so two of them can write at the same time.
in the default sqlite mode a writer blocks readers, and a second writer can fail with database is locked.
wal mode lets reads go on while a write is happening, and the busy timeout makes a second writer wait up to 5 seconds and not fail at once.
these are only set when the database is sqlite, a postgres url is left alone.

inserting features in batches
at first every feature was built as an sqlalchemy object and attached to the file before saving.
for a big file that is a lot of objects in memory at once.
now the features are plain rows that are inserted 1000 at a time.
i kept it as one transaction and did not commit each batch, because a file with only some of its features saved would give wrong totals.
the file is still read into memory in one go by geopandas, so this helps with the database part and not with the reading part.

pinned versions
requirements.txt pins the packages the app uses directly, but numpy, pandas, pydantic and others come in through them and were not pinned.
the measurement numbers depend on those too, so constraints.txt pins every installed package and pip is run with it.
i used a constraints file and not a second tool like poetry or uv, so the setup is still plain pip.
the base image in the Dockerfile is pinned by its digest for the same reason, the 3.12-slim tag is moved to a new image every few weeks.

pagination on features and measurements
a file can have thousands of features and returning all of them in one response would be slow.

summary endpoint
once the measurements are paginated the client cant get a total without fetching every page.
the totals are worked out by the database with one grouped query, so it does not load the features into python.

units are converted when reading, not when storing
the database always has square metres and metres.
the unit is only a query param on the measurements and summary endpoints.
this way the same file can be read in hectares by one client and acres by another, and nothing has to be measured again.
the allowed units are a fixed list, so a wrong unit is rejected by fastapi with a 422 before any query runs.

kmz and geojson
kmz is what google earth saves by default, so a kml only service would reject a lot of real files.
it is read from inside the archive like the shapefile zip, nothing is extracted.
geojson was added because the reader already supports it, it was one small function.

list and delete
without a list endpoint an id that was lost could never be found again.
delete removes the file row and its features together, the features are removed through the sqlalchemy relationship cascade.

features crossing the 180 degree line
the projection is centred on the feature, so the only thing that broke at the 180 line was finding the centre.
in my test a small polygon across the line was 0.02 percent off and a line was more than 5 times too long.
moving the longitudes to 0 to 360 before taking the centre fixed both, and they now match the same shape placed at 0 degrees.
i did not split the geometry at the line, because the projection does not care about the line once its centre is right.

docker
the app can run without docker, because the gdal library comes inside the pyogrio wheel.
the Dockerfile is there because the numbers depend on the gdal and proj versions, and the image pins them together with python, so every machine measures with the same libraries.
i built the image and ran the same upload tests against the container, and every measurement matched running it directly to at least 11 digits.
i built it again after pinning the base image and the packages, and checked the upload, a failed file, the 413 for a body that is too big, the log lines and the health check inside the container.
the container runs as a normal user and not root.
the database is in a volume, so the files are still there after the container is restarted or replaced.
it has a health check that calls /health.
the image is about 710 MB, most of it is the geospatial libraries.
i used the slim python image and not alpine, because the pyogrio and shapely wheels are built for glibc and alpine would have to compile gdal.

what an edge between two points means
a file only stores the corner points, it does not say what the line between them looks like, and for a big shape that changes the area.
i looked at how other projects handle it.
postgis has two types, geometry treats an edge as a straight line in the coordinates, and geography treats it as the shortest path on the earth.
qgis measures on the ellipsoid when one is set for the project, and pyproj has geodesic area and length built in.
the geojson spec says an edge is a straight line in lon lat and warns that it can be far from the geodesic.
i went with the geodesic for files in lon lat, because that is what postgis geography, qgis and pyproj give, so the numbers can be checked against them.
for files in a projected crs i kept the straight line in that crs, because that is what the file means and what postgis geometry does.
before this a square with only 4 points was 0.004 percent off at 1 degree wide and 0.4 percent off at 10 degrees.
now it is within 0.00004 percent of the geodesic area at every size i tested, up to 120 degrees wide.
the points are only added for measuring, the stored geometry is not changed.
there is a cap of 10000 points on one ring, so a bad file cant make the server build millions of points.

one file per upload
the upload takes one file, like the assignment says.
if two files came in the same request the second one used to replace the first without any message.
now it is a 400 with a clear message, which is better than quietly dropping a file.
i did not make it process many files at once, because the response is one file record and that would change the api.

cors
a browser blocks a web page from calling an api on another address unless the api allows it.
a map page that uploads files to this service would hit that, so the api sends the cors headers.
it allows any origin by default because there is no login and no cookies, and CORS_ORIGINS can limit it to a list.

tests
the assignment does not ask for tests.
i added them because the measurement numbers are easy to get wrong without noticing, so the tests compare them with geodesic values from pyproj.
there are 63 tests and they run every line and every branch of the app code.
this is checked on every run by pytest-cov, and the run fails if coverage drops below 100 percent.
a github actions workflow installs the pinned packages on a clean linux machine and runs the same tests on every push.
i ran the same steps in a clean linux container before adding it, and all 63 tests passed there.
some check the result from outside through the api, and some call one function and compare it with a value worked out by hand.
for example one degree along the equator has to be 6378137 times pi divided by 180 metres, and a 100 m square at the centre of a utm zone has to be 10000 divided by 0.9996 squared square metres.
there is also a test that sends 16 uploads from 8 threads to a real sqlite file and checks that all of them are stored.


known limits

in a lon lat file an edge always takes the shortest way round the earth, so one edge cant be longer than half way round.
a geojson file is measured with geodesic edges like every other lon lat file, even though the geojson spec says straight lines in lon lat, the two only differ for edges that are many km long.
a shape that covers more than half of the earth is not measured correctly.
a zip with more than one shapefile is rejected.
a kmz with more than one kml inside only has doc.kml read, or the first kml if there is no doc.kml.
geojson is only accepted with the .geojson extension, not .json.
kml files come back with a few extra properties like tessellate and extrude, these are added by the kml driver.
a kml column that is empty for every feature is left out of the properties, because the kml driver adds many columns that are always empty, so a field that was really in the file but empty everywhere is dropped too.
an upload sent without a content length is still received in full before the size limit stops it.
the whole file is read into memory, so a very big file needs that much memory.
the tables are created on startup and there are no migrations, so changing a column later needs a manual step.


learning

measuring in degrees is not the only mistake, picking any projected crs is also not enough, web mercator and even utm gave numbers that were measurably off.
checking results against a second method, geodesic in this case, is what showed the problem with utm.
a shapefile is really several files and it can be missing its crs, so the reader has to check before trusting it.
kml stores each folder as its own layer and every geometry has a z value.
the 180 degree line only breaks things if the code depends on the middle of the longitudes, the projection itself is fine with it.
a shape can be valid on the earth and invalid in lon lat, so validity has to be checked in the plane where it is measured.
error text from a library can carry server paths, so it has to be cleaned before it is shown to a client.
testing with odd files found more bugs than testing with good ones, like a geojson with no properties and a line with two identical points.
sqlite does not keep the timezone of a datetime, so the time has to be marked as utc again when it is read back.
the same corner points can mean different shapes, and postgis, qgis and the geojson spec do not all agree on which one.
building the docker image and testing inside it is the only way to know the Dockerfile works, reading it is not enough.
keeping the measurement code separate from fastapi made it much easier to test.
catching an error and returning a nice message hides bugs unless the error is also logged.
fastapi reads the upload body before it runs dependencies, so a check that has to happen before the body must be a middleware.
pinning only the packages i import is not the same as pinning what gets installed.


future scope

background processing with a job queue for very large files, with the client polling the status.
support for geopackage and other formats.
an option to choose between geodesic and straight edges for lon lat files.
uploading several files in one request and getting a list back.
postgres with postgis if spatial queries are needed, like finding features inside a bounding box.
authentication and per user files.
automatic cleanup of old files.
schema migrations with alembic.
reading big files in pieces so the whole file is not in memory.
a request id in the logs and in the error response.
