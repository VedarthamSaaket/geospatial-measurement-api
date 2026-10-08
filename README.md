geospatial file measurement api

this is a backend service that takes a geospatial file and gives back measurements for the features inside it.
you upload a kml file or a zip that has a shapefile in it.
the service reads every feature, stores it, and works out the area for polygons and the length for lines.
points are stored but they dont get a measurement.
it is built with fastapi, sqlalchemy, sqlite, geopandas, shapely and pyproj.


what each file does

app/main.py creates the fastapi app, sets up the database on startup and plugs in the routes.
app/config.py holds the settings like where data is stored, the max upload size and the allowed file types.
app/database.py creates the sqlalchemy engine and the session that each request uses.
app/models.py has the two tables, one for uploaded files and one for the features inside them.
app/schemas.py has the pydantic models that shape the json responses.
app/routes.py has the api endpoints.
app/services.py handles an upload from start to finish, it saves the file, reads it, measures every feature and stores the result.
app/readers.py reads a kml or a zipped shapefile into a geodataframe and figures out the crs.
app/measure.py has the measurement logic, it picks a projection for each feature and calculates area or length.
tests/conftest.py has the test client and helpers that build sample kml and shapefile zips.
tests/test_measure.py tests the measurement logic directly.
tests/test_api.py tests the endpoints with real uploads.
requirements.txt lists the python packages.
Dockerfile runs the app in a container if you dont want to set up python.


setup

you need python 3.11 or newer.

```
git clone <repo url>
cd geospatial-measurement-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

the api runs on http://localhost:8000 and the interactive docs are on http://localhost:8000/docs.
a data folder is created on first run and it holds the sqlite database.
you can change the location with the DATA_DIR env variable, and the upload limit with MAX_UPLOAD_MB, the default is 50.

to run the tests

```
python -m pytest
```

to run it with docker instead

```
docker build -t geo-api .
docker run -p 8000:8000 geo-api
```


api

POST /api/files/
uploads and processes a file.
it is a multipart form upload and the field name is file.
it accepts a .kml file or a .zip that contains exactly one shapefile with its .shp, .shx and .dbf parts.

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
it returns 415 if the extension is not .kml or .zip, 400 if the file is empty and 413 if it is bigger than the limit.
it returns 422 if the file has the right extension but cant be read, and the body has status FAILED with the reason.

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

GET /api/files/{id}/
returns information about an uploaded file.
the response is the same shape as the upload response above.
it returns 404 if the id does not exist.

```
curl http://localhost:8000/api/files/01fee8eece33463d9c3b9da6d57ec8d1/
```

GET /api/files/{id}/measurements/
returns the measurement for every feature in the file.
it takes limit and offset query params, limit is 100 by default and 1000 at most.

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
      "value": 1534.3104335972616,
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

GET /api/files/{id}/features/
returns the stored features with their geometry and properties.
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
the upload comes in and the extension is checked first.
the file is written to disk in 1 MB chunks and rejected if it goes over the size limit.
a kml is opened layer by layer, because every folder in a kml is a separate layer, and the layers are joined into one table.
a zip is checked to make sure it has exactly one .shp and its .shx and .dbf, then it is read straight from the zip without extracting it.
the crs is taken from the file.
each feature gets an index, its geometry type, its geometry as geojson, its properties and its measurement, and all of it is saved in one transaction.
the uploaded file is deleted from disk after that because everything needed is in the database.
if the file cant be read, the file record is still saved with status FAILED and the reason.

measurement calculation flow
a feature with no geometry gets no measurement and a note saying so.
points and multipoints get no measurement.
any other type that is not a polygon or a line, like a geometry collection, gets no measurement and a note, it does not crash the upload.
the z value is dropped because area and length are measured on the ground.
if a polygon is invalid, like a bowtie shape, it is repaired first and a note is added.
the geometry is converted to lon lat, then to a projection made for that feature, and then shapely calculates the area or the length.
multipolygons and multilines work the same way, the parts are added up, and holes in polygons are subtracted.
area is in square metres and length is in metres.

crs handling
nothing is ever measured in degrees.
every geometry is first converted from the file crs to EPSG:4326, even if the file was already in a projected crs.
i do this because a projected crs is not always good for measuring, web mercator for example makes areas much bigger than they are.
then for each feature i build a projection centred on the middle of that feature.
for polygons it is a lambert azimuthal equal area projection, which keeps area correct.
for lines it is an azimuthal equidistant projection, which keeps distances correct close to its centre.
the projection that was used is returned in measurement_crs so the result can be checked.
kml is always EPSG:4326 by its spec.
if a shapefile has no .prj file and all the coordinates fit inside lon lat ranges, i assume EPSG:4326 and set crs_assumed to true.
if it has no .prj and the coordinates dont look like lon lat, the features are stored but not measured, because guessing would give wrong numbers.
the stored geometry stays in the original crs of the file, only the measurement uses the projected version.


design decisions

fastapi instead of django
the service has four endpoints and no admin, auth or templates, so django would be mostly unused.
fastapi also gives request validation and the /docs page for free.
django with drf would make more sense if this grew into a bigger app with users and permissions.

sqlite with sqlalchemy
sqlite needs no setup so anyone can clone and run it.
sqlalchemy is used so moving to postgres later is a change of the DATABASE_URL and not a rewrite.
i thought about postgres with postgis but the service does no spatial queries, it only stores and returns features, so geometry is kept as geojson in a json column.

geopandas with pyogrio for reading
both shapefile and kml are read by the same library, so there is one code path after the file is opened.
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
the client still gets every other feature.
only a file that cant be opened at all is marked FAILED.

failed uploads are saved
an unreadable file returns 422 but the record is kept with the error, so GET /api/files/{id}/ can show what went wrong later.

pagination on features and measurements
a file can have thousands of features and returning all of them in one response would be slow.

docker
docker is not needed to run this, because the gdal library comes inside the pyogrio wheel.
i still added a small Dockerfile for anyone who does not want to install python.

tests
the assignment does not ask for tests.
i added them because the measurement numbers are easy to get wrong without noticing, so the tests compare them with geodesic values from pyproj.


known limits

a feature that crosses the 180 degree line will be measured wrong.
for very large features the edges between points are treated as straight lines in the projection, so the result depends on how many points the shape has.
length for a line that is thousands of km long is less accurate, because azimuthal equidistant is only exact for distances from its centre.
a zip with more than one shapefile is rejected.
kmz files are not supported.
kml files come back with a few extra properties like tessellate and extrude, these are added by the kml driver.


learning

measuring in degrees is not the only mistake, picking any projected crs is also not enough, web mercator and even utm gave numbers that were measurably off.
checking results against a second method, geodesic in this case, is what showed the problem with utm.
a shapefile is really several files and it can be missing its crs, so the reader has to check before trusting it.
kml stores each folder as its own layer and every geometry has a z value.
keeping the measurement code separate from fastapi made it much easier to test.


future scope

background processing with a job queue for very large files, with the client polling the status.
support for kmz, geojson and geopackage.
handling of features that cross the 180 degree line.
splitting long edges into smaller pieces before projecting, for better accuracy on very large features.
postgres with postgis if spatial queries are needed, like finding features inside a bounding box.
an option to pick the units, like hectares or km.
authentication and per user files.
a delete endpoint and cleanup of old files.
