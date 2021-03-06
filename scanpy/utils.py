# Copyright 2016-2017 F. Alexander Wolf (http://falexwolf.de).
"""
Utility functions and classes
"""

from __future__ import absolute_import
import os
from collections import OrderedDict

import numpy as np
from . import settings as sett

#--------------------------------------------------------------------------------
# Deal with examples
#--------------------------------------------------------------------------------

def fill_in_datakeys(dexamples, dexdata):
    """
    Update the 'examples dictionary' _examples.dexamples.

    If a datakey (key in 'datafile dictionary') is not present in the 'examples
    dictionary' it is used to initialize an entry with that key.
    
    If not specified otherwise, any 'exkey' (key in 'examples dictionary') is
    used as 'datakey'.
    """
    # default initialization of 'datakey' key with entries from data dictionary
    for exkey in dexamples:
        if 'datakey' not in dexamples[exkey]:
            if exkey in dexdata:
                dexamples[exkey]['datakey'] = exkey
            else:
                dexamples[exkey]['datakey'] = 'unspecified in dexdata'
    return dexamples

#--------------------------------------------------------------------------------
# Deal with tool parameters
#--------------------------------------------------------------------------------

def update_params(old_params, new_params, check=False):
    """
    Update old_params with new_params.

    If check==False, this merely adds and overwrites the content of old_params.

    If check==True, this only allows updating of parameters that are already
    present in old_params.

    Parameters
    ----------
    old_params : dict
    new_params : dict
    check : bool, optional (default: False)

    Returns
    -------
    updated_params : dict
    """
    updated_params = dict(old_params)
    if new_params: # allow for new_params to be None
        for key, val in new_params.items():
            if not key in old_params and check:
                raise ValueError('\'' + key 
                                 + '\' is not a valid parameter key, '
                                 + 'consider one of \n' 
                                 + str(list(old_params.keys())))
            if val is not None:
                updated_params[key] = val
    return updated_params

#--------------------------------------------------------------------------------
# Command-line argument reading and processing
#--------------------------------------------------------------------------------

def add_args(p, dadd_args=None):
    """
    Add arguments to parser.

    Parameters
    -------
    dadd_args : dict
        Dictionary of additional arguments formatted as 
            {'arg': {'type': int, 'default': 0, ... }}
    """

    aa = p.add_argument_group('Tool parameters').add_argument
    aa('exkey',
       type=str, default='', metavar='exkey',
       help='The "example key" is used to look up data and default parameters. '
            'Use subcommand "examples" to display possible values.')
    # example key default argument
    aa('-o', '--oparams',
       nargs='*', default=None, metavar='k v',
       help='Optional tool parameters as list, e.g., "k 20 knn True", '
            'see detailed help above, also note the '
            'option --opfile (default: "").')
    # arguments from dadd_args
    if dadd_args is not None:
        for key, val in dadd_args.items():
            if key != 'arg':
                aa(key, **val)
    # make sure there are is no conflict with dadd_args
    if dadd_args is None or '--opfile' not in dadd_args:
        aa('--opfile',
           type=str, default='', metavar='f',
           help='Path to file with optional parameters (default: "").')

    aa = p.add_argument_group('Plot parameters').add_argument
    aa('-p', '--pparams',
       nargs='*', default=None, metavar='k v',
       help='Plotting parameters as list, '
            'e.g., "layout 3d comps 1,3,4". ' 
            'Display possible paramaters via "-p help" (default: "").')

    # standard arguments
    p = sett.add_args(p)

    return p

def read_args_tool(toolkey, dexamples, tool_add_args=None):
    """
    Read args for single tool.
    """
    import scanpy as sc
    p = default_tool_argparser(sc.help(toolkey, string=True), dexamples)
    if tool_add_args is None:
        p = add_args(p)
    else:
        p = tool_add_args(p)
    args = vars(p.parse_args())
    args = sett.process_args(args)
    return args

def default_tool_argparser(description, dexamples):
    """
    Create default parser for single tools.
    """
    import argparse
    epilog = '\n'
    for k,v in sorted(dexamples.items()):
        epilog += '  ' + k + '\n'
    p = argparse.ArgumentParser(
        description=description,
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=('available values for examples (exkey):'+epilog))
    return p

#--------------------------------------------------------------------------------
# Others
#--------------------------------------------------------------------------------

def select_groups(adata, groups_names_subset='all', smp='groups'):
    """
    Get subset of groups in adata.smp[smp].
    """
    groups_names = adata[smp + '_names']
    if smp + '_masks' in adata:
        groups_masks = adata[smp + '_masks']
    else:
        groups_masks = np.zeros((len(adata[smp + '_names']),
                                        adata.smp[smp].size), dtype=bool)
        for iname, name in enumerate(adata[smp + '_names']):
            # if the name is not found, fallback to index retrieval
            if adata[smp + '_names'][iname] in adata.smp[smp]:
                mask = adata[smp + '_names'][iname] == adata.smp[smp]
            else:
                mask = str(iname) == adata.smp[smp]
            groups_masks[iname] = mask
    groups_ids = list(range(len(groups_names)))
    if groups_names_subset != 'all':
        # get list from string
        if isinstance(groups_names_subset, str):
            groups_names_subset = groups_names_subset.split(',')
        groups_ids = np.where(np.in1d(adata[smp + '_names'], np.array(groups_names_subset)))[0]
        if len(groups_ids) == 0:
            # fallback to index retrieval
            groups_ids = np.where(np.in1d(np.arange(len(adata[smp + '_names'])).astype(str),
                                          np.array(groups_names_subset)))[0]
        if len(groups_ids) == 0:
            sett.m(0, np.array(groups_names_subset), 
                   'invalid! specify valid groups_names (or indices) one of',
                   adata[smp + '_names'])
            from sys import exit
            exit(0)
        groups_masks = groups_masks[groups_ids]
        groups_names_subset = adata[smp + '_names'][groups_ids]
    else:
        groups_names_subset = groups_names
    return groups_names_subset, groups_masks

def pretty_dict_string(d, indent=0):
    """
    Pretty output of nested dictionaries.
    """
    s = ''
    for key, value in sorted(d.items()):
        s += '    ' * indent + str(key)
        if isinstance(value, dict):
             s += '\n' + pretty_dict_string(value, indent+1)
        else:
             s += ' = ' + str(value) + '\n'
    return s

def markdown_dict_string(d):
    """
    Markdown output that can be pasted in the examples/README.md.
    """
    # sort experimental data from simulated data
    from collections import OrderedDict
    types = OrderedDict()
    for key, value in sorted(d.items()):
        if 'type' in value:
            if value['type'] not in types:
                types[value['type']] = []
            types[value['type']].append(key)
        else:
            print(key, 'does not define data type!')
    # format output
    s = ''
    for type in ['scRNAseq', 'scqPCR', 'bulk', 'simulated']:
        s += '\nExamples using ' + type + ' data.\n'
        for key in types[type]:
            value = d[key]
            s += '* [' + key + '](#' + key + ')'
            if 'ref' in value:
                if 'doi' in value:
                    link = 'http://dx.doi.org/' + value['doi']
                elif 'url' in value:
                    link = value['url']
                s += (' - [' +  value['ref'].replace('et al.','*et al.*') 
                             + '](' + link +  ')')
            if 'title' in value:
                s += '   \n*' + value['title'] + '*'
            s += '\n'
    return s

def merge_dicts(*dicts):
    """
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.

    Note
    ----
    http://stackoverflow.com/questions/38987/how-to-merge-two-python-dictionaries-in-a-single-expression
    """
    result = {}
    for d in dicts:
        result.update(d)
    return result

def masks(list_of_index_lists,n):
    """
    Make an array in which rows store 1d mask arrays from list of index lists.

    Parameters
    ----------
    n : int
        Maximal index / number of samples.
    """
    # make a list of mask arrays, it's easier to store 
    # as there is a hdf5 equivalent
    for il,l in enumerate(list_of_index_lists):
        mask = np.zeros(n,dtype=bool)
        mask[l] = True
        list_of_index_lists[il] = mask
    # convert to arrays
    masks = np.array(list_of_index_lists)
    return masks

def warn_with_traceback(message, category, filename, lineno, file=None, line=None):
    """
    Get full tracebacks when warning is raised by setting

    warnings.showwarning = warn_with_traceback
    
    See also
    --------
    http://stackoverflow.com/questions/22373927/get-traceback-of-warnings
    """
    import warnings
    import traceback
    traceback.print_stack()
    log = file if hasattr(file,'write') else sys.stderr
    sett.write(warnings.formatwarning(message, category, filename, lineno, line))

def subsample(X,subsample=1,seed=0):
    """ 
    Subsample a fraction of 1/subsample samples from the rows of X.

    Parameters
    ----------
    X : np.ndarray
        Data array.
    subsample : int
        1/subsample is the fraction of data sampled, n = X.shape[0]/subsample.
    seed : int
        Seed for sampling.

    Returns
    -------
    Xsampled : np.ndarray
        Subsampled X.
    rows : np.ndarray 
        Indices of rows that are stored in Xsampled.
    """
    if subsample == 1 and seed == 0:
        return X, np.arange(X.shape[0],dtype=int)
    if seed == 0:
        # this sequence is defined simply by skipping rows
        # is faster than sampling
        rows = np.arange(0,X.shape[0],subsample,dtype=int)
        n = rows.size
        Xsampled = np.array(X[rows])
    if seed > 0:
        n = int(X.shape[0]/subsample)
        np.random.seed(seed)
        Xsampled, rows = subsample_n(X,n=n)
    sett.m(0,'subsampled to',n,'of',X.shape[0],'data points')
    return Xsampled, rows

def subsample_n(X,n=0,seed=0):
    """ 
    Subsample n samples from rows of array.

    Parameters
    ----------
    X : np.ndarray
        Data array.
    seed : int
        Seed for sampling.

    Returns
    -------
    Xsampled : np.ndarray
        Subsampled X.
    rows : np.ndarray 
        Indices of rows that are stored in Xsampled.
    """
    if n < 0:
        raise ValueError('n must be greater 0')
    np.random.seed(seed)
    n = X.shape[0] if (n == 0 or n > X.shape[0]) else n
    rows = np.random.choice(X.shape[0],size=n,replace=False)
    Xsampled = np.array(X[rows])
    return Xsampled, rows

def comp_distance(X, metric='euclidean'):
    """ 
    Compute distance matrix for data array X
    
    Parameters
    ----------
    X : np.ndarray
        Data array (rows store samples, columns store variables).
    metric : string
        For example 'euclidean', 'sqeuclidean', see sp.spatial.distance.pdist.

    Returns
    -------
    D : np.ndarray
        Distance matrix.
    """
    from scipy.spatial import distance
    D = distance.pdist(X, metric=metric)
    D = distance.squareform(D)
    sett.mt(0, 'computed distance matrix with metric =', metric)
    return D

def hierarch_cluster(M):
    """ 
    Cluster matrix using hierarchical clustering.

    Parameters
    ----------
    M : np.ndarray
        Matrix, for example, distance matrix.

    Returns
    -------
    Mclus : np.ndarray 
        Clustered matrix.
    indices : np.ndarray
        Indices used to cluster the matrix.
    """
    import scipy as sp
    import scipy.cluster
    link = sp.cluster.hierarchy.linkage(M)
    indices = sp.cluster.hierarchy.leaves_list(link)
    Mclus = np.array(M[:,indices])
    Mclus = Mclus[indices,:]
    sett.mt(0,'clustered matrix')
    if False:
        pl.matshow(Mclus)
        pl.colorbar()
    return Mclus, indices

def check_datafile_deprecated(filename, ext=None):
    """
    Check whether the file is present and is not just a placeholder.

    If the file is not present at all, look for a file with the same name but
    ending on '_url.txt', and try to download the datafile from there.

    If the file size is below 500 Bytes, assume the file is just a placeholder
    for a link to github. Download from github in this case.
    """
    if filename.startswith('sim/'):
        if not os.path.exists(filename):
            exkey = filename.split('/')[1]
            print('file ' + filename + ' does not exist')
            print('you can produce the datafile by')
            exit('running subcommand "sim ' + exkey + '"')
    if ext is None:
        _, ext = os.path.splitext()
    if ext.startswith('.'):
        ext = ext[1:]
    if not os.path.exists(filename) and not os.path.exists('../'+filename):
        basename = filename.replace('.'+ext,'')
        urlfilename = basename + '_url.txt'
        if not os.path.exists(urlfilename):
            urlfilename = '../' + urlfilename
        if not os.path.exists(urlfilename):
            raise ValueError('Neither ' + filename + 
                             ' nor ../' + filename +
                             ' nor files with a url to download from exist \n' + 
                             '--> move your data file to one of these places \n' +
                             '    or cd/browse into scanpy root directory.')
        with open(urlfilename) as f:
            url = f.readline().strip()
        sett.m(0,'data file is not present \n' + 
              'try downloading data file from url \n' + url + '\n' + 
              '... this may take a while but only happens once')
        # download the file
        urlretrieve(url,filename,reporthook=download_progress)
        sett.m(0,'')

    rel_filename = filename
    if not os.path.exists(filename):
        rel_filename = '../' + filename

    # if file is smaller than 500 Bytes = 0.5 KB
    threshold = 500
    if os.path.getsize(rel_filename) < threshold:
        # download the file
        # note that this has 'raw' in the address
        github_baseurl = r'https://github.com/theislab/scanpy/raw/master/'
        fileurl = github_baseurl + filename
        sett.m(0,'size of file',rel_filename,'is below',threshold/1000.,' kilobytes') 
        sett.m(0,'--> presumably is a placeholder for a git-lfs file')
        sett.m(0,'... if you installed git-lfs, you can use \'git lfs checkout\'')
        sett.m(0,'... to update all files with their actual content') 
        sett.m(0,'--> downloading data file from github using url')
        sett.m(0,fileurl)
        sett.m(0,'... this may take a while but only happens once')
        # make a backup of the small file
        from shutil import move
        basename = rel_filename.replace('.'+ext,'')
        move(rel_filename,basename+'_placeholder.txt')
        # download the file
        try:
            urlretrieve(fileurl,rel_filename,reporthook=download_progress)
            sett.m(0,'')
        except Exception as e:
            sett.m(0,e)
            sett.m(0,'when calling urlretrieve() in module scanpy.utils.utils')
            sett.m(0,'--> is the github repo/url private?')
            sett.m(0,'--> if you have access, manually download the file')
            sett.m(0,fileurl)
            sett.m(0,'replace the small file',rel_filename,'with the downloaded file')
            quit()

    return rel_filename

def odict_merge(*ds):
    merged = OrderedDict()
    for d in ds:
        for k, v in d.items():
            merged[k] = v
    return merged
