"""
    pyexcel_io.sqlbook
    ~~~~~~~~~~~~~~~~~~~

    The lower level handler for database import and export

    :copyright: (c) 2014-2016 by Onni Software Ltd.
    :license: New BSD License, see LICENSE for more details
"""
from ..book import BookReader, BookWriter
from ..sheet import SheetReader, SheetWriter, NamedContent
from ..manager import RWManager
from ..utils import from_query_sets, is_empty_array, swap_empty_string_for_none
from ..constants import (
    MESSAGE_INVALID_PARAMETERS,
    MESSAGE_EMPTY_ARRAY,
    MESSAGE_IGNORE_ROW,
    DB_SQL
)


class PyexcelSQLSkipRowException(Exception):
    """
    Raised this exception to skipping a row
    while data import
    """
    pass


class SQLTableReader(SheetReader):
    """Read a table
    """
    def __init__(self, session, table):
        self.session = session
        self.table = table

    def to_array(self):
        objects = self.session.query(self.table).all()
        if len(objects) == 0:
            return []
        else:
            column_names = sorted([column for column in objects[0].__dict__
                                   if column != '_sa_instance_state'])
            return from_query_sets(column_names, objects)


class SQLTableWriter(SheetWriter):
    """Write to a table
    """
    def __init__(self, session, table_params, auto_commit=True, **keywords):
        self.session = session
        self.table = None
        self.initializer = None
        self.mapdict = None
        self.column_names = None
        self.auto_commit = auto_commit
        self.keywords = keywords
        if len(table_params) == 4:
            (self.table, self.column_names,
             self.mapdict, self.initializer) = table_params
        else:
            raise ValueError(MESSAGE_INVALID_PARAMETERS)

        if isinstance(self.mapdict, list):
            self.column_names = self.mapdict
            self.mapdict = None

    def write_row(self, array):
        if is_empty_array(array):
            print(MESSAGE_EMPTY_ARRAY)
        else:
            new_array = swap_empty_string_for_none(array)
            try:
                self._write_row(new_array)
            except PyexcelSQLSkipRowException:
                print(MESSAGE_IGNORE_ROW)
                print(new_array)

    def _write_row(self, array):
        row = dict(zip(self.column_names, array))
        obj = None
        if self.initializer:
            # allow initinalizer to return None
            # if skipping is needed
            obj = self.initializer(row)
        if obj is None:
            obj = self.table()
            for name in self.column_names:
                if self.mapdict is not None:
                    key = self.mapdict[name]
                else:
                    key = name
                setattr(obj, key, row[name])
        self.session.add(obj)

    def close(self):
        if self.auto_commit:
            self.session.commit()


class SQLTableExportAdapter(object):
    def __init__(self, table):
        self.table = table

    def get_name(self):
        return getattr(self.table, '__tablename__', None)


class SQLTableExporter(object):
    def __init__(self, session):
        self.session = session
        self.adapters = []

    def append(self, import_adapter):
        self.adapters.append(import_adapter)


class SQLBookReader(BookReader):
    def __init__(self):
        BookReader.__init__(self, DB_SQL)

    def open(self, file_name, **keywords):
        raise NotImplementedError()

    def open_stream(self, file_stream, **keywords):
        raise NotImplementedError()

    def open_content(self, file_content, **keywords):
        self.exporter = file_content
        self._load_from_tables()

    def read_sheet(self, native_sheet):
        reader = SQLTableReader(self.exporter.session, native_sheet.payload)
        return reader.to_array()

    def _load_from_tables(self):
        tables = self.exporter.adapters
        self.native_book = [NamedContent(adapter.get_name(), adapter.table)
                            for adapter in tables]


class SQLTableImportAdapter(SQLTableExportAdapter):
    def __init__(self, table):
        SQLTableExportAdapter.__init__(self, table)
        self.row_initializer = None
        self.column_names = None
        self.column_name_mapping_dict = None


class SQLTableImporter(object):
    def __init__(self, session):
        self.session = session
        self.adapters = {}

    def append(self, import_adapter):
        self.adapters[import_adapter.get_name()] = import_adapter

    def get(self, name):
        return self.adapters.get(name, None)


class SQLBookWriter(BookWriter):
    def __init__(self):
        BookWriter.__init__(self, DB_SQL)

    def open_content(self, file_content, **keywords):
        self.importer = file_content

    def create_sheet(self, sheet_name):
        sheet_writer = None
        adapter = self.importer.get(sheet_name)
        if adapter:
            sheet_writer = SQLTableWriter(
                    self.importer.session,
                    (adapter.table, adapter.column_names,
                     adapter.column_name_mapping_dict,
                     adapter.row_initializer)
            )
        return sheet_writer

RWManager.register_a_reader(DB_SQL, SQLBookReader)
RWManager.register_a_writer(DB_SQL, SQLBookWriter)