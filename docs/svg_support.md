# SVG Support Notes

The drawing loader uses `svgpathtools` to parse drawable vector geometry into
paper-space strokes. Covered fixtures include lines, multiple paths, curves, and
path transforms.

Unsupported or not-yet-modeled SVG features include text-only artwork, raster
images, paint styling, clipping, masks, and semantic grouping beyond the geometry
that `svgpathtools` can flatten into paths.
