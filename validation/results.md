# Flood mask evaluation

## Balasore, Odisha · Cyclone Dana, October 2024

| Radar observations | Independent reference | Eligible study area | Precision | Recall | F1 | IoU |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Sentinel-1A on 28 Oct at 00:05 UTC. Baseline from 29 Aug, 10 Sep, 22 Sep, 4 Oct and 16 Oct. | JAXA ALOS-2 on 26 Oct | 52.882 km² (99.60%) | 35.21% | 30.28% | 32.56% | 19.44% |

JAXA generated the flood proxy automatically from ALOS-2. Sentinel Asia lists the shapefile set under **Flood Proxy Map 2024-10-26**. The site policy permits scientific and educational use. Credit belongs to JAXA and Sentinel Asia. The source archive is stored locally under ignored `data/local/`. [Event and product listing](https://sentinel-asia.org/EO/2024/article20241025IN.html) · [Site policy](https://sentinel-asia.org/sitepolicy/SitePolicy.html).

### Method and eligibility

The script replays the [bundled Balasore case](../data/demo_events/balasore-2024/event.json) with the same study polygon, Sentinel-1 scene IDs, and `sar-vv-1` parameters. The replay reproduced the saved 554.95 ha detection and the same rendered change pixels. The full study area sampled by the radar grid covered 5,309.64 ha.

The script projects the JAXA `REGION` and `FLDEXT` polygons to EPSG:6933. A 10 m grid cell is eligible when its center is inside the JAXA product region and the cell is in the study area and has finite before and after radar values. Eligible cells within `FLDEXT` count as reference positives. The 21.44 ha outside the JAXA region were excluded. All radar cells within the region had valid before and after observations. The comparison retains radar terrain exclusions as part of the prediction, so a reference-positive pixel screened out by the radar method counts as a miss.

| Comparison with the JAXA proxy | Area (ha) |
| --- | ---: |
| Mapped by both | 194.90 |
| Mapped by SAR Translator only | 358.62 |
| Mapped by JAXA only | 448.82 |
| Neither product mapped flood | 4,285.86 |
| Eligible radar detection | 553.52 |
| Eligible JAXA mapped flood | 643.72 |

Precision is shared mapped area divided by eligible radar detection. Recall is shared mapped area divided by eligible JAXA flood area. IoU is shared area divided by the union. F1 is the harmonic mean of precision and recall.

### Interpretation

Only 19.44% of the combined mapped extent overlapped. The observations were two calendar days apart, and floodwater can recede or shift in that interval. The ALOS-2 proxy and the Sentinel-1 comparison also differ in sensor, baseline and processing. Reference negatives signify an absence of JAXA mapped flood within the published region. The archive does not include field labels or a separate pixel-level validity layer. The figures measure agreement between products for one event. General accuracy, performance by land-cover type, and calibration of High/Medium/Low observation quality require a separate evaluation dataset.

### Reproduce

With the optional Earth Engine dependencies installed and `EE_PROJECT_ID` configured, run this from the project root. The script verifies the SHA-256 of the downloaded archive and prints the metrics as JSON.

```powershell
New-Item -ItemType Directory -Force data/local | Out-Null
curl.exe -fL -o data/local/cyclone-dana-alos2.zip https://sentinel-asia.org/EO/2024/article20241025IN/JAXA/JAXA_20241026_FPM_ALOS2_India_FLDEXT.zip
.venv/Scripts/python.exe -m validation.balasore data/local/cyclone-dana-alos2.zip
```
