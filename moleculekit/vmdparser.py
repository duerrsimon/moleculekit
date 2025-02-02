# (c) 2015-2022 Acellera Ltd http://www.acellera.com
# All Rights Reserved
# Distributed under HTMD Software License Agreement
# No redistribution in whole or part
#
import ctypes as ct
import logging
import os
import platform

import numpy as np
from moleculekit.home import home
from moleculekit.support import pack_string_buffer, pack_int_buffer, pack_double_buffer

logger = logging.getLogger(__name__)

libdir = home(libDir=True)
if platform.system() == "Windows":
    ct.cdll.LoadLibrary(os.path.join(libdir, "libgcc_s_seh-1.dll"))
    ct.cdll.LoadLibrary(os.path.join(libdir, "libstdc++-6.dll"))
    if os.path.exists(os.path.join(libdir, "psprolib.dll")):
        ct.cdll.LoadLibrary(os.path.join(libdir, "psprolib.dll"))
    parser = ct.cdll.LoadLibrary(os.path.join(libdir, "libvmdparser.dll"))
else:
    parser = ct.cdll.LoadLibrary(os.path.join(libdir, "libvmdparser.so"))


def vmdselection(
    selection,
    coordinates,
    atomname,
    atomtype,
    resname,
    resid,
    chain=None,
    segname=None,
    insert=None,
    altloc=None,
    beta=None,
    occupancy=None,
    bonds=None,
):

    maxseglen = np.max([len(x) for x in segname])
    if maxseglen > 4:
        logger.warning(
            "More than 4 characters were used for segids. "
            "Due to limitations in VMD atomselect segids will be ignored for the atomselection."
        )
        segname = segname.copy()
        segname[:] = ""

    if coordinates.ndim == 2:
        coordinates = np.atleast_3d(coordinates)

    if coordinates.shape[1] != 3:
        print(coordinates.shape)
        raise RuntimeError("Coordinates needs to be natoms x 3 x nframes")

    if coordinates.dtype != np.float32:
        raise ValueError("Coordinates is not float32")

    if coordinates.strides[0] != 12 or coordinates.strides[1] != 4:
        # It's a view -- need to make a copy to ensure contiguity of memory
        coordinates = np.array(coordinates, dtype=np.float32)
    if coordinates.strides[0] != 12 or coordinates.strides[1] != 4:
        raise ValueError("Coordinates is a view with unsupported strides")

    natoms = coordinates.shape[0]
    nframes = coordinates.shape[2]
    # Sanity check the inputs

    if bonds is not None and bonds.shape[1] != 2:
        raise RuntimeError("'bonds' not nbonds x 2 in length")
    if len(atomname) != natoms:
        #        print(natoms)
        #        print(len(atomname))
        raise RuntimeError("'atomname' not natoms in length")
    if len(atomtype) != natoms:
        raise RuntimeError("'atomtype' not natoms in length")
    if len(resname) != natoms:
        raise RuntimeError("'resname' not natoms in length")
    if len(resid) != natoms:
        raise RuntimeError("'resid' not natoms in length")
    if chain is not None and len(chain) != natoms:
        raise RuntimeError("'chain' not natoms in length")
    if segname is not None and len(segname) != natoms:
        raise RuntimeError("'segname' not natoms in length")
    if insert is not None and len(insert) != natoms:
        raise RuntimeError("'insert' not natoms in length")
    if altloc is not None and len(altloc) != natoms:
        raise RuntimeError("'altloc' not natoms in length")
    if beta is not None and len(beta) != natoms:
        raise RuntimeError("'beta' not natoms in length")
    if occupancy is not None and len(occupancy) != natoms:
        raise RuntimeError("'occupancy' not natoms in length")

    c_selection = ct.create_string_buffer(selection.encode("ascii"), len(selection) + 1)
    c_natoms = ct.c_int(natoms)
    c_nframes = ct.c_int(nframes)
    c_atomname = pack_string_buffer(atomname)
    c_atomtype = pack_string_buffer(atomtype)
    c_resname = pack_string_buffer(resname)
    c_resid = pack_int_buffer(resid)
    c_chain = None
    c_segname = None
    c_insert = None
    c_altloc = None
    c_beta = None
    c_occupancy = None

    c_coords = None

    c_nbonds = None
    c_bonds = None

    if chain is not None:
        c_chain = pack_string_buffer(chain)
    if segname is not None:
        c_segname = pack_string_buffer(segname)
    if insert is not None:
        c_insert = pack_string_buffer(insert)
    if altloc is not None:
        c_altloc = pack_string_buffer(altloc)
    if beta is not None:
        c_beta = pack_double_buffer(beta)
    if occupancy is not None:
        c_occupancy = pack_double_buffer(occupancy)

    c_bonds = None
    nbonds = 0

    if bonds is not None:  # TODO: Replace the loops for bonds with ravel
        nbonds = bonds.shape[0]
        if nbonds > 0:
            c_bonds = pack_int_buffer(bonds.reshape(-1).copy())

    c_nbonds = ct.c_int(nbonds)

    ll = natoms * nframes
    c_output_buffer = (ct.c_int * ll)()

    c_coords = coordinates.ctypes.data_as(ct.POINTER(ct.c_float))

    retval = parser.atomselect(
        c_selection,
        c_natoms,
        c_beta,
        c_occupancy,
        c_atomtype,
        c_atomname,
        c_resname,
        c_resid,
        c_chain,
        c_segname,
        c_insert,
        c_altloc,
        c_coords,
        c_nframes,
        c_nbonds,
        c_bonds,
        c_output_buffer,
    )

    if retval != 0:
        raise RuntimeError(
            f'Could not parse selection "{selection}". Is the selection a valid VMD atom selection?'
        )

    retval = np.empty((natoms, nframes), dtype=np.bool_)

    for frame in range(nframes):
        for atom in range(natoms):
            retval[atom, frame] = c_output_buffer[frame * natoms + atom]

    return np.squeeze(retval)


#    return (retval.reshape(natoms, nframes))


def guessbonds(
    coordinates, element, name, resname, resid, chain, segname, insertion, altloc
):
    # if it's a single frame, resize to be a 3d array
    if coordinates.ndim == 2:
        c = coordinates.shape
        coordinates = coordinates.reshape((c[0], c[1], 1))

    if coordinates.shape[2] > 1:
        raise ValueError("Coordinates must be a single frame")

    if coordinates.strides[0] != 12 or coordinates.strides[1] != 4:
        # It's a view -- need to make a copy to ensure contiguity of memory
        coordinates = np.array(coordinates, dtype=np.float32)
    if coordinates.strides[0] != 12 or coordinates.strides[1] != 4:
        raise ValueError("Coordinates is a view with unsupported strides")

    if coordinates.dtype != np.float32:
        raise ValueError("Coordinates is not float32")
    natoms = coordinates.shape[0]
    nframes = coordinates.shape[2]

    if len(element) != natoms:
        raise RuntimeError("'element' not natoms in length")
    if len(name) != natoms:
        raise RuntimeError("'name' not natoms in length")
    if len(resname) != natoms:
        raise RuntimeError("'resname' not natoms in length")
    if len(resid) != natoms:
        raise RuntimeError("'resid' not natoms in length")

    c_natoms = ct.c_int(natoms)
    c_element = pack_string_buffer(element)
    c_name = pack_string_buffer(name)
    c_resname = pack_string_buffer(resname)

    c_chain = pack_string_buffer(chain)
    c_segname = pack_string_buffer(segname)
    c_insert = pack_string_buffer(insertion)
    c_altLoc = pack_string_buffer(altloc)
    c_resid = pack_int_buffer(resid)
    c_nframes = ct.c_int(nframes)

    c_nbonds = (ct.c_int * 1)()
    maxbonds = (
        natoms * 5
    )  # some dumb guess about the max # of bonds likely to be created
    tmp = maxbonds * 2
    c_bonds = (ct.c_int * tmp)()

    c_nbonds[0] = 0
    c_coords = coordinates.ctypes.data_as(ct.POINTER(ct.c_float))

    retval = parser.guessbonds(
        c_natoms,
        c_nframes,
        c_name,
        c_element,
        c_resname,
        c_resid,
        c_chain,
        c_segname,
        c_insert,
        c_altLoc,
        c_coords,
        c_nbonds,
        ct.c_int(maxbonds),
        c_bonds,
    )

    if retval:
        raise RuntimeError("Failed at guessing bonding")

    nbonds = c_nbonds[0]
    bonds = np.array(c_bonds[: nbonds * 2]).reshape(nbonds, 2).astype(np.uint32).copy()
    return bonds
