#!/usr/bin/env python
# Copyright 2016-2017 F. Alexander Wolf (http://falexwolf.de).
"""
Test Data-Graph class
"""

import numpy as np
from matplotlib import pyplot as pl
from sys import path
path.insert(0, '.')
import scanpy as sc

def test_shortest_path():

    # chain layout
    n = 5
    X = np.arange(n)[:, np.newaxis]

    params = {}
    params['k'] = 2
    params['knn'] = True
    params['sigma'] = 0
    params['n_pcs'] = 30
    params['fates'] = {'test': 4}
    ct = sc.tools.paths.Commute(X, params)
    ct.iroot = 3

    dct = ct.diffmap()
    ct.compute_M_matrix()
    ct.compute_Ddiff_matrix()

    ct.set_pseudotimes()
    ct.fates_paths()

    print(ct.pathids_n)

def test_distance_metrics():

    # TODO: investigate quality of approximation!

    # chain layout
    n = 1000
    num_evals = 10
    norm = True
    show = True

    X = np.arange(n)[:, np.newaxis]

    params = {}
    params['k'] = 2
    params['knn'] = True
    params['sigma'] = 0
    params['n_pcs'] = 30
    from scanpy import graph
    ct = graph.DataGraph(X, params)

    ct.compute_transition_matrix(weighted=False, 
                                 neglect_selfloops=True, 
                                 alpha=0)
    print(ct.K)

    ct.compute_Ddiff_all(num_evals)
    evalsT = ct.evals
    # dpt distance
    if show:
        pl.matshow(ct.Ddiff)
        pl.title('Ddiff')
        pl.colorbar()
    else:
        print(ct.Ddiff)

    # commute distance
    ct.compute_C_all(num_evals)
    evalsL = ct.evals
    if show:
        pl.matshow(ct.C)
        pl.title('C')
        pl.colorbar()
    else:
        print(ct.C)

    # MFP distance
#     ct.compute_MFP_matrix()
#     if show:
#         pl.matshow(ct.MFP)
#         pl.title('MFP')
#         pl.colorbar()
#     else:
#         print(ct.MFP)

    i = 0 #int(n/2)
    normDdiff = np.max(ct.Ddiff[i]) if norm else 1
    normC = np.max(ct.C[i]) if norm else 1
#     normMFP = np.max(ct.MFP[i]) if norm else 1
    pl.figure()
    pl.plot(ct.Ddiff[i]/normDdiff, label='Ddiff')
    pl.plot(ct.C[i]/normC, label='C')
#     pl.plot(ct.MFP[i]/normMFP, label='MFP')
    pl.legend()

    pl.figure()
    pl.plot(evalsT/normDdiff, label='evalsT')
    pl.plot(evalsL/normC, label='evalsL')
    pl.legend()
    pl.show()

if __name__ == '__main__':
    #test_shortest_path()
    test_distance_metrics()
