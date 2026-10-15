# Uniform-height object positioning

Complete 6,433 × 14 workbook generation with 333 data-review comments.
20 timing runs per version/case, five per rotating physical-core pair.
Five separate memory runs per version/case. Memory is peak newly traced Python allocation, not process RAM.
The two workbook cases use public taxi records. This is a constructed workflow, not a measurement of a deployed application.
Every archive member is compared byte-for-byte outside the measurement.

<details>
<summary>Show every measured case and core pair</summary>

| Row overrides | Core mask | Base time | PR time | Speed | Base peak | PR peak | Memory |
|---|---|---:|---:|---|---:|---:|---|
| none (uniform height) | 0x300 | 1952.864 ms | 1500.690 ms | 1.301× faster | 23.406072 MiB | 23.405915 MiB | 1.000007× less |
| none (uniform height) | 0xc00 | 1881.506 ms | 1492.828 ms | 1.260× faster | 23.406072 MiB | 23.405915 MiB | 1.000007× less |
| none (uniform height) | 0xf | 618.696 ms | 472.070 ms | 1.311× faster | 23.406072 MiB | 23.405915 MiB | 1.000007× less |
| none (uniform height) | 0xf0 | 705.925 ms | 474.628 ms | 1.487× faster | 23.406072 MiB | 23.405915 MiB | 1.000007× less |
| custom header (original path) | 0x300 | 1941.075 ms | 2245.789 ms | 1.157× slower | 23.406460 MiB | 23.406425 MiB | 1.000002× less |
| custom header (original path) | 0xc00 | 1897.993 ms | 1929.511 ms | 1.017× slower | 23.406460 MiB | 23.406425 MiB | 1.000002× less |
| custom header (original path) | 0xf | 715.651 ms | 604.687 ms | 1.184× faster | 23.406460 MiB | 23.406425 MiB | 1.000002× less |
| custom header (original path) | 0xf0 | 767.500 ms | 729.082 ms | 1.053× faster | 23.406460 MiB | 23.406425 MiB | 1.000002× less |

</details>

Memory medians belong to each workbook case, not to each individual core pair.
All samples, fixture hashes and source hashes are in the JSON.
