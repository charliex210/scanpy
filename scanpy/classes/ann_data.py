"""
Annotated Data
"""
from collections import Mapping, Sequence
from collections import OrderedDict
from enum import Enum
import numpy as np
from numpy import ma
from numpy.lib.recfunctions import append_fields
from scipy import sparse as sp
from scipy.sparse.sputils import IndexMixin
from ..utils import odict_merge

class StorageType(Enum):
    Array = np.ndarray
    Masked = ma.MaskedArray
    Sparse = sp.spmatrix

    @classmethod
    def classes(cls):
        return tuple(c.value for c in cls.__members__.values())

SMP_NAMES = 'smp_names'
VAR_NAMES = 'var_names'

class BoundRecArr(np.recarray):
    """
    A np.recarray which can be constructed from a dict.
    Is bound to AnnData to allow adding fields
    """
    def __new__(cls, source, name_col, parent, n_row=None):
        if source is None:  # empty array
            cols = [np.arange(n_row)]
            dtype = [(name_col, 'int64')]
        elif isinstance(source, np.recarray):
            cols = [source[n] for n in source.dtype.names]
            dtype = source.dtype
        else:
            if not isinstance(source, Mapping):
                raise ValueError(
                    'meta needs to be a recarray or dictlike, not {}'
                    .format(type(source)))
            # meta is dict-like
            names = list(source.keys())
            cols = [np.asarray(col) for col in source.values()]
            if name_col not in source:
                names.append(name_col)
                cols.append(np.arange(len(cols[0]) if cols else n_row))
            dtype = list(zip(names, [str(c.dtype) for c in cols]))
        try:
            dtype = np.dtype(dtype)
        except TypeError:
            # TODO: fix compat with Python 2
            # print(dtype, file=sys.stderr)
            raise

        arr = np.recarray.__new__(cls, (len(cols[0]),), dtype)
        arr._parent = parent
        arr._name_col = name_col

        for i, name in enumerate(dtype.names):
            arr[name] = np.array(cols[i])

        return arr

    def flipped(self):
        old_name_col = self._name_col
        new_name_col = SMP_NAMES if old_name_col == VAR_NAMES else VAR_NAMES

        flipped = BoundRecArr(self, new_name_col, self._parent, len(self))
        flipped.dtype.names = tuple(
            new_name_col if n == old_name_col else n
            for n in self.dtype.names)

        return flipped

    def copy(self):
        new = super(BoundRecArr, self).copy()
        new._name_col = self._name_col
        new._parent = self._parent
        return new

    @property
    def columns(self):
        return [c for c in self.dtype.names if not c == self._name_col]

    def __setitem__(self, keys, values):
        if isinstance(keys, str):
            keys = [keys]
            values = [values]
        keys = np.array(keys)
        values = np.array(values)  # sequence of arrays or matrix with n_key *rows*
        if not len(keys) == len(values):
            raise ValueError('You passed {} column keys but {} arrays as columns. '
                             'If you passed a matrix instead of a sequence of arrays, try transposing it.'
                             .format(len(keys), len(values)))

        present = np.intersect1d(keys, self.dtype.names)
        absent = np.setdiff1d(keys, self.dtype.names)

        if any(present):
            for k, v in zip(present, values[np.in1d(keys, present)]):
                super(BoundRecArr, self).__setitem__(k, v)

        if any(absent):
            attr = 'smp' if self._name_col == SMP_NAMES else 'var'
            if values.shape[1] > len(self):
                raise ValueError('New column has too many entries ({} > {})'
                                 .format(values.shape[1], len(self)))
            source = append_fields(self, absent, values[np.in1d(keys, absent)],
                                   usemask=False, asrecarray=True)
            new = BoundRecArr(source, self._name_col, self._parent)
            setattr(self._parent, attr, new)

def _check_dimensions(data, smp, var):
    n_smp, n_var = data.shape
    if len(smp) != n_smp:
        raise ValueError('Sample metadata needs to have the same amount of '
                         'rows as data has ({}), but has {} rows'
                         .format(n_smp, smp.shape[0]))
    if len(var) != n_var:
        raise ValueError('Feature metadata needs to have the same amount of '
                         'rows as data has columns ({}), but has {} rows'
                         .format(n_var, var.shape[0]))

class AnnData(IndexMixin):
    def __init__(self, ddata_or_X=None, smp=None, var=None, **add):
        """
        Annotated Data

        Stores a data matrix X of dimensions n_samples x n_variables,
        e.g. n_cells x n_genes, with the possibility to store an arbitrary
        number of annotations for both samples and variables, and
        additional arbitrary unstructured annotation via **add.

        You can access additional annotation elements directly from AnnData:
        >>> adata = AnnData(np.eye(3), k=1)
        >>> assert adata['k'] == 1

        Parameters
        ----------
        ddata_or_X : dict, np.ndarray, np.ma.MaskedArray, sp.spmatrix
            The data matrix or a dict containing the data matrix and possibly
            X : np.ndarray, np.ma.MaskedArray, sp.spmatrix
                A n_samples x n_variables data matrix.
            row_names / smp_names : list, np.ndarray, optional
                A n_samples array storing names for samples.
            col_names / var_names : list, np.ndarray, optional
                A n_variables array storing names for variables.
            row / smp : dict, optional
                A dict with row annotation.
            col / var : dict, optional
                A dict with row annotation.
        smp : np.recarray, dict
            A n_samples x ? record array containing sample names (`smp_names`)
            and other sample annotation in the columns. A passed dict is
            converted to a record array.
        var : np.recarray, dict
            The same as `smp`, but of shape n_variables x ? for annotation of
            variables.
        **add : dict
            Unstructured annotation for the whole dataset.

        Attributes
        ----------
        X, smp, var from the Parameters.
        """
        if isinstance(ddata_or_X, Mapping):
            if any((smp, var, add)):
                raise ValueError('If ddata_or_X is a dict, it needs to contain all metadata')
            X, smp, var, add = self.from_ddata(ddata_or_X)
        else:
            X = ddata_or_X

        # check data type of X
        for s_type in StorageType:
            if isinstance(X, s_type.value):
                self.storage_type = s_type
                break
        else:
            class_names = ', '.join(c.__name__ for c in StorageType.classes())
            raise ValueError(
                'X needs to be of one of the following types [{}] not {}'
                .format(class_names, type(X)))

        if len(X.shape) == 1:
            X.shape = (X.shape[0], 1)
        if X.dtype.names is None and len(X.shape) != 2:
            raise ValueError('X needs to be 2-dimensional, not '
                             '{}D'.format(len(X.shape)))

        n_smp, n_var = X.shape

        self.X = X

        self.smp = BoundRecArr(smp, SMP_NAMES, self, n_smp)
        self.var = BoundRecArr(var, VAR_NAMES, self, n_var)

        _check_dimensions(X, self.smp, self.var)

        self.add = add

    def from_ddata(self, ddata):
        smp, var = OrderedDict(), OrderedDict()

        add = dict(ddata.items())
        del ddata

        X = add['X']
        del add['X']

        if 'row_names' in add:
            smp['smp_names'] = add['row_names']
            del add['row_names']
        elif 'smp_names' in add:
            smp['smp_names'] = add['smp_names']
            del add['smp_names']

        if 'col_names' in add:
            var['var_names'] = add['col_names']
            del add['col_names']
        elif 'var_names' in add:
            var['var_names'] = add['var_names']
            del add['var_names']

        smp = odict_merge(smp, add.get('row', {}), add.get('smp', {}))
        var = odict_merge(var, add.get('col', {}), add.get('var', {}))
        for k in ['row', 'smp', 'col', 'var']:
            if k in add:
                del add[k]

        return X, smp, var, add

    def to_ddata(self):
        smp = OrderedDict([(k, self.smp[k]) for k in self.smp_keys()])
        var = OrderedDict([(k, self.var[k]) for k in self.var_keys()])
        d = {'X': self.X, 'smp': smp, 'var': var,
             'smp_names': self.smp_names, 'var_names': self.var_names}
        for k, v in self.add.items():
            d[k] = v
        return d

    def smp_keys(self):
        return [n for n in self.smp.dtype.names if n != SMP_NAMES]

    def var_keys(self):
        return [n for n in self.var.dtype.names if n != VAR_NAMES]

    @property
    def smp_names(self):
        return self.smp[SMP_NAMES]

    @smp_names.setter
    def smp_names(self, keys):
        self.smp[SMP_NAMES] = keys

    @property
    def var_names(self):
        return self.var[VAR_NAMES]

    @var_names.setter
    def var_names(self, keys):
        self.var[VAR_NAMES] = keys

    def __setattr__(self, key, value):
        names_col = dict(smp=SMP_NAMES, var=VAR_NAMES).get(key)
        if names_col and not isinstance(value, BoundRecArr):  # if smp/var is set, give it the right class
            names_orig, dim = (self.smp_names, 0) if names_col == SMP_NAMES else (self.var_names, 1)
            value_orig, value = value, BoundRecArr(value, names_col, self)
            if len(value) != self.X.shape[dim]:
                raise ValueError('New value for {!r} was converted to a reacarray of length {} instead of {}'
                                 .format(key, len(value_orig), len(self)))
            if (value[names_col] == np.arange(self.X.shape[dim])).all():  # TODO: add to constructor
                value[names_col] = names_orig
        object.__setattr__(self, key, value)

    def _normalize_indices(self, packed_index):
        smp, var = super(AnnData, self)._unpack_index(packed_index)
        smp = self._normalize_index(smp, self.smp_names)
        var = self._normalize_index(var, self.var_names)
        return smp, var

    def _normalize_index(self, index, names):
        def name_idx(i):
            if isinstance(i, str):
                # `where` returns an 1-tuple (1D array) of found indices
                i = np.where(names == i)[0][0]
                if i is None:
                    raise IndexError('Index {} not in smp_names/var_names'
                                     .format(index))
            return i

        if isinstance(index, slice):
            start = name_idx(index.start)
            stop = name_idx(index.stop)
            # string slices can only be inclusive, so +1 in that case
            if isinstance(index.stop, str):
                stop = None if stop is None else stop + 1
            step = index.step
        elif isinstance(index, (int, str)):
            start = name_idx(index)
            stop = start + 1
            step = 1
        elif isinstance(index, (Sequence, np.ndarray)):
            return np.fromiter(map(name_idx, index), 'int64')
        else:
            raise IndexError('Unknown index {!r} of type {}'
                             .format(index, type(index)))

        return slice(start, stop, step)

    def __delitem__(self, index):
        smp, var = self._normalize_indices(index)
        del self.X[smp, var]
        if var == slice(None):
            del self.smp.iloc[smp, :]
        if smp == slice(None):
            del self.var.iloc[var, :]

    def __getitem__(self, index):
        # return element from add if index is string
        if isinstance(index, str):
            return self.add[index]
        # otherwise unpack index
        smp, var = self._normalize_indices(index)
        X = self.X[smp, var]
        smp_ann = self.smp[smp]
        var_ann = self.var[var]
        assert smp_ann.shape[0] == X.shape[0], (smp, smp_ann)
        assert var_ann.shape[0] == X.shape[1], (var, var_ann)
        adata = AnnData(X, smp_ann, var_ann,  **self.add)
        return adata

    def __setitem__(self, index, val):
        if isinstance(index, str):
            self.add[index] = val
            return

        smp, var = self._normalize_indices(index)
        self.X[smp, var] = val

    def __contains__(self, item):
        return item in self.add

    def get(self, key, default=None):
        return self.add.get(key, default)

    def __len__(self):
        return self.X.shape[0]

    def transpose(self):
        return AnnData(self.X.T, self.var.flipped(), self.smp.flipped(), **self.add)

    T = property(transpose)

def test_creation():
    AnnData(np.array([[1, 2], [3, 4]]))
    AnnData(ma.array([[1, 2], [3, 4]], mask=[0, 1, 1, 0]))
    AnnData(sp.eye(2))
    AnnData(
        np.array([[1, 2, 3], [4, 5, 6]]),
        dict(Smp=['A', 'B']),
        dict(Feat=['a', 'b', 'c']))

    assert AnnData(np.array([1, 2])).X.shape == (2, 1)

    from pytest import raises
    raises(ValueError, AnnData,
           np.array([[1, 2], [3, 4]]),
           dict(TooLong=[1, 2, 3, 4]))

def test_ddata():
    ddata = dict(
        X=np.array([[1, 2, 3], [4, 5, 6]]),
        row_names=['A', 'B'],
        col_names=['a', 'b', 'c'])
    AnnData(ddata)

def test_names():
    adata = AnnData(
        np.array([[1, 2, 3], [4, 5, 6]]),
        dict(smp_names=['A', 'B']),
        dict(var_names=['a', 'b', 'c']))

    assert adata.smp_names.tolist() == 'A B'.split()
    assert adata.var_names.tolist() == 'a b c'.split()

def test_get_subset():
    mat = AnnData(np.array([[1, 2, 3], [4, 5, 6]]))

    assert mat[0, 0].X.tolist() == [[1]]
    assert mat[0, :].X.tolist() == [[1, 2, 3]]
    assert mat[:, 0].X.tolist() == [[1], [4]]
    assert mat[:, [0, 1]].X.tolist() == [[1, 2], [4, 5]]
    assert mat[:, np.array([0, 2])].X.tolist() == [[1, 3], [4, 6]]
    assert mat[:, np.array([False, True, True])].X.tolist() == [[2, 3], [5, 6]]
    assert mat[:, 1:3].X.tolist() == [[2, 3], [5, 6]]

def test_get_subset_names():
    mat = AnnData(
        np.array([[1, 2, 3], [4, 5, 6]]),
        dict(smp_names=['A', 'B']),
        dict(var_names=['a', 'b', 'c']))

    assert mat['A', 'a'].X.tolist() == [[1]]
    assert mat['A', :].X.tolist() == [[1, 2, 3]]
    assert mat[:, 'a'].X.tolist() == [[1], [4]]
    assert mat[:, ['a', 'b']].X.tolist() == [[1, 2], [4, 5]]
    assert mat[:, np.array(['a', 'c'])].X.tolist() == [[1, 3], [4, 6]]
    assert mat[:, 'b':'c'].X.tolist() == [[2, 3], [5, 6]]

    from pytest import raises
    with raises(IndexError): _ = mat[:, 'X']
    with raises(IndexError): _ = mat['X', :]
    with raises(IndexError): _ = mat['A':'X', :]
    with raises(IndexError): _ = mat[:, 'a':'X']

def test_transpose():
    mat = AnnData(
        np.array([[1, 2, 3], [4, 5, 6]]),
        dict(smp_names=['A', 'B']),
        dict(var_names=['a', 'b', 'c']))

    mt1 = mat.T

    # make sure to not modify the original!
    assert mat.smp_names.tolist() == ['A', 'B']
    assert mat.var_names.tolist() == ['a', 'b', 'c']

    assert SMP_NAMES in mt1.smp.dtype.names
    assert VAR_NAMES in mt1.var.dtype.names
    assert mt1.smp_names.tolist() == ['a', 'b', 'c']
    assert mt1.var_names.tolist() == ['A', 'B']
    assert mt1.X.shape == mat.X.T.shape

    mt2 = mat.transpose()
    assert np.array_equal(mt1.X, mt2.X)
    assert np.array_equal(mt1.smp, mt2.smp)
    assert np.array_equal(mt1.var, mt2.var)

def test_get_subset_add():
    mat = AnnData(np.array([[1, 2, 3], [4, 5, 6]]),
                  dict(Smp=['A', 'B']),
                  dict(Feat=['a', 'b', 'c']))

    assert mat[0, 0].smp['Smp'].tolist() == ['A']
    assert mat[0, 0].var['Feat'].tolist() == ['a']

def test_append_add_col():
    mat = AnnData(np.array([[1, 2, 3], [4, 5, 6]]))

    mat.smp['new'] = [1, 2]
    mat.smp[['new2', 'new3']] = [['A', 'B'], ['c', 'd']]

    from pytest import raises
    with raises(ValueError):
        mat.smp['new4'] = 'far too long'.split()

def test_set_add():
    mat = AnnData(np.array([[1, 2, 3], [4, 5, 6]]))

    mat.smp = dict(smp_names=[1, 2])
    assert isinstance(mat.smp, BoundRecArr)
    assert len(mat.smp.dtype) == 1

    mat.smp = dict(a=[1, 2])  # leave smp_names and a custom column
    assert isinstance(mat.smp, BoundRecArr)
    assert len(mat.smp.dtype) == 2
    assert mat.smp_names.tolist() == [1, 2]

    from pytest import raises
    with raises(ValueError):
        mat.smp = dict(a=[1, 2, 3])
