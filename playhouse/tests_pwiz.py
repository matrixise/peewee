import os
import re
import unittest

from peewee import *
from pwiz import *
from peewee import print_


TEST_VERBOSITY = int(os.environ.get('PEEWEE_TEST_VERBOSITY') or 1)

# test databases
sqlite_db = SqliteDatabase('tmp.db')
try:
    import MySQLdb
    mysql_db = MySQLDatabase('peewee_test')
except ImportError:
    mysql_db = None
try:
    import psycopg2
    postgres_db = PostgresqlDatabase('peewee_test')
except ImportError:
    postgres_db = None

DATABASES = (
    ('Sqlite', sqlite_db),
    ('MySQL', mysql_db),
    ('Postgres', postgres_db))

class BaseModel(Model):
    class Meta:
        database = sqlite_db

class ColTypes(BaseModel):
    f1 = BigIntegerField()
    f2 = BlobField()
    f3 = BooleanField()
    f4 = CharField()
    f5 = DateField()
    f6 = DateTimeField()
    f7 = DecimalField()
    f8 = DoubleField()
    f9 = FloatField()
    f10 = IntegerField()
    f11 = PrimaryKeyField()
    f12 = TextField()
    f13 = TimeField()

class Nullable(BaseModel):
    nullable_cf = CharField(null=True)
    nullable_if = IntegerField(null=True)

class RelModel(BaseModel):
    col_types = ForeignKeyField(ColTypes, related_name='foo')
    col_types_nullable = ForeignKeyField(ColTypes, null=True)

class FKPK(BaseModel):
    col_types = ForeignKeyField(ColTypes, primary_key=True)

class Underscores(BaseModel):
    _id = PrimaryKeyField()
    _name = CharField()


DATABASES = (
    (sqlite_db, 'sqlite'),
    (mysql_db, 'mysql'),
    (postgres_db, 'postgres'),
)

MODELS = (
    ColTypes,
    Nullable,
    RelModel,
    FKPK,
    Underscores)

class TestPwiz(unittest.TestCase):
    def test_sqlite_fk_re(self):
        user_id_tests = [
            'FOREIGN KEY("user_id") REFERENCES "users"("id")',
            'FOREIGN KEY(user_id) REFERENCES users(id)',
            'FOREIGN KEY  ([user_id])  REFERENCES  [users]  ([id])',
            '"user_id" NOT NULL REFERENCES "users" ("id")',
            'user_id not null references users (id)',
        ]
        fk_pk_tests = [
            ('"col_types_id" INTEGER NOT NULL PRIMARY KEY REFERENCES '
             '"coltypes" ("f11")'),
            'FOREIGN KEY ("col_types_id") REFERENCES "coltypes" ("f11")',
        ]
        regex = SqliteIntrospector.re_foreign_key

        for test in user_id_tests:
            match = re.search(regex, test, re.I)
            self.assertEqual(match.groups(), (
                'user_id', 'users', 'id',
            ))

        for test in fk_pk_tests:
            match = re.search(regex, test, re.I)
            self.assertEqual(match.groups(), (
                'col_types_id', 'coltypes', 'f11',
            ))

    def create_tables(self, db):
        for model in MODELS:
            model._meta.database = db
            model.create_table(True)

    def generative_test(fn):
        def inner(self):
            for database, db_name in DATABASES:
                if database:
                    self.create_tables(database)
                    fn(self, database, db_name)
                elif TEST_VERBOSITY > 0:
                    print_('Skipping %s, driver not found' % db_name)
        return inner

    def introspect(self, database, db_name):
        db = get_introspector(db_name, database.database)
        return introspect(db, None)

    @generative_test
    def test_col_types(self, database, db_name):
        models, _, _, _ = self.introspect(database, db_name)
        coltypes = models['coltypes']

        expected = (
            ('coltypes', (
                ('f1', BigIntegerField, False),
                ('f2', BlobField, False),
                ('f3', (BooleanField, IntegerField), False),
                ('f4', CharField, False),
                ('f5', DateField, False),
                ('f6', DateTimeField, False),
                ('f7', DecimalField, False),
                ('f8', (DoubleField, FloatField), False),
                ('f9', FloatField, False),
                ('f10', IntegerField, False),
                ('f11', PrimaryKeyField, False),
                ('f12', TextField, False),
                ('f13', TimeField, False))),
            ('relmodel', (
                ('col_types_id', ForeignKeyField, False),
                ('col_types_nullable_id', ForeignKeyField, True))),
            ('nullable', (
                ('nullable_cf', CharField, True),
                ('nullable_if', IntegerField, True))),
            ('fkpk', (
                ('col_types_id', ForeignKeyField, False),)),
            ('underscores', (
                ('_id', PrimaryKeyField, False),
                ('_name', CharField, False))),
        )

        for table, table_cols in expected:
            data = models[table]
            for field, klass, nullable in table_cols:
                if not isinstance(klass, (list, tuple)):
                    klass = (klass,)
                column_info = data[field]
                self.assertTrue(
                    column_info.field_class in klass,
                    '[%s] %s %s not in %s' % (
                        db_name, table, column_info.field_class, klass))
                self.assertEqual(
                    column_info.kwargs.get('null', False),
                    nullable)

    @generative_test
    def test_foreign_keys(self, database, db_name):
        _, _, table_fks, _ = self.introspect(database, db_name)
        self.assertEqual(table_fks['coltypes'], [])

        rm = table_fks['relmodel']
        self.assertEqual(len(rm), 2)

        fkpk = table_fks['fkpk']
        self.assertEqual(len(fkpk), 1)
        fkpk_fk = fkpk[0]
        self.assertEqual(fkpk_fk.column, 'col_types_id')
        self.assertEqual(fkpk_fk.table, 'coltypes')
        self.assertEqual(fkpk_fk.pk, 'f11')

    @generative_test
    def test_table_names(self, database, db_name):
        _, table_to_model, _, _ = self.introspect(database, db_name)
        names = (
            ('coltypes', 'Coltypes'),
            ('nullable', 'Nullable'),
            ('relmodel', 'Relmodel'),
            ('fkpk', 'Fkpk'))
        for k, v in names:
            self.assertEqual(table_to_model[k], v)

    @generative_test
    def test_column_meta(self, database, db_name):
        _, _, _, col_meta = self.introspect(database, db_name)
        rm_meta = col_meta['relmodel']

        self.assertEqual(rm_meta['col_types_id'], {
            'db_column': "'col_types_id'",
            'rel_model': 'Coltypes'})
        self.assertEqual(rm_meta['col_types_nullable_id'], {
            'db_column': "'col_types_nullable_id'",
            'rel_model': 'Coltypes',
            'null': True})

        fkpk_meta = col_meta['fkpk']
        self.assertEqual(fkpk_meta['col_types_id'], {
            'db_column': "'col_types_id'",
            'rel_model': 'Coltypes',
            'primary_key': True})
