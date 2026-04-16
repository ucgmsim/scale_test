#!/bin/bash
#SBATCH --job-name=sw4_strong_64
#SBATCH --account=nesi00213
#SBATCH --ntasks=64
#SBATCH --nodes=1
#SBATCH --time=02:00:00
#SBATCH --output=sw4_strong_64_%j.out
#SBATCH --error=sw4_strong_64_%j.err

module purge
module load \
    NeSI/zen3 \
    rclone/1.62.2 \
    GCCcore/12.3.0 \
    zlib/1.2.13-GCCcore-12.3.0 \
    binutils/2.40-GCCcore-12.3.0 \
    GCC/12.3.0 \
    numactl/2.0.16-GCCcore-12.3.0 \
    UCX/1.18.1-GCCcore-12.3.0 \
    UCC/1.3.0-GCCcore-12.3.0 \
    OpenMPI/4.1.5-GCC-12.3.0 \
    OpenBLAS/0.3.23-GCC-12.3.0 \
    FlexiBLAS/3.3.1-GCC-12.3.0 \
    FFTW/3.3.10-GCC-12.3.0 \
    gompi/2023a \
    FFTW.MPI/3.3.10-gompi-2023a \
    ScaLAPACK/2.2.0-gompi-2023a-fb \
    foss/2023a \
    bzip2/1.0.8-GCCcore-12.3.0 \
    XZ/5.4.2-GCCcore-12.3.0 \
    libpng/1.6.40-GCCcore-12.3.0 \
    freetype/2.13.2-GCCcore-12.3.0 \
    Szip/2.1.1-GCCcore-12.3.0 \
    HDF5/1.14.3-gompi-2023a \
    libjpeg-turbo/2.1.5.1-GCCcore-12.3.0 \
    ncurses/6.4-GCCcore-12.3.0 \
    libreadline/8.2-GCCcore-12.3.0 \
    libxml2/2.11.4-GCCcore-12.3.0 \
    libxslt/1.1.38-GCCcore-12.3.0 \
    OpenSSL/1.1 \
    cURL/8.3.0-GCCcore-12.3.0 \
    zstd/1.5.5-GCCcore-12.3.0 \
    netCDF/4.9.2-gompi-2023a \
    SQLite/3.42.0-GCCcore-12.3.0 \
    Tcl/8.6.10-GCCcore-12.3.0 \
    Tk/8.6.10-GCCcore-12.3.0 \
    ZeroMQ/4.3.5-GCCcore-12.3.0 \
    Python/3.11.6-foss-2023a \
    PCRE2/10.42-GCCcore-12.3.0 \
    json-c/0.17-GCC-12.3.0 \
    expat/2.5.0-GCCcore-12.3.0 \
    OpenJPEG/2.5.0-GCCcore-12.3.0 \
    KEALib/1.5.2-gompi-2023a \
    LibTIFF/4.5.1-GCCcore-12.3.0 \
    PROJ/9.3.0-GCC-12.3.0 \
    libgeotiff/1.7.1-GCC-12.3.0-PROJ-9.3.0 \
    lz4/1.9.4-GCCcore-12.3.0 \
    snappy/1.1.10-GCCcore-12.3.0 \
    Arrow/14.0.1-GCC-12.3.0 \
    libKML/1.3.0.2017-GCC-12.3.0 \
    GDAL/3.6.4-gompi-2023a \
    GEOS/3.11.3-GCC-12.3.0 \
    GMT/6.6.0-foss-2023a

SW4="/nesi/project/nesi00213/tools/sw4"
INPUT="/nesi/project/nesi00213/scale_test/flow/events/input_strong.in"

mpirun $SW4 $INPUT
