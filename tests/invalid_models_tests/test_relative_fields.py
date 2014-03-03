# -*- encoding: utf-8 -*-
from __future__ import unicode_literals

from django.core.checks import Error
from django.db import models
from django.test.utils import override_settings
from django.test.testcases import skipIfDBFeature

from .base import IsolatedModelsTestCase


class RelativeFieldTests(IsolatedModelsTestCase):

    def test_valid_foreign_key_without_accessor(self):
        class Target(models.Model):
            # There would be a clash if Model.field installed an accessor.
            model = models.IntegerField()

        class Model(models.Model):
            field = models.ForeignKey(Target, related_name='+')

        field = Model._meta.get_field('field')
        errors = field.check()
        self.assertEqual(errors, [])

    def test_foreign_key_to_missing_model(self):
        # Model names are resolved when a model is being created, so we cannot
        # test relative fields in isolation and we need to attach them to a
        # model.
        class Model(models.Model):
            foreign_key = models.ForeignKey('Rel1')

        field = Model._meta.get_field('foreign_key')
        errors = field.check()
        expected = [
            Error(
                ("Field defines a relation with model 'Rel1', "
                 "which is either not installed, or is abstract."),
                hint=None,
                obj=field,
                id='fields.E300',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_many_to_many_to_missing_model(self):
        class Model(models.Model):
            m2m = models.ManyToManyField("Rel2")

        field = Model._meta.get_field('m2m')
        errors = field.check(from_model=Model)
        expected = [
            Error(
                ("Field defines a relation with model 'Rel2', "
                 "which is either not installed, or is abstract."),
                hint=None,
                obj=field,
                id='fields.E300',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_ambiguous_relationship_model(self):

        class Person(models.Model):
            pass

        class Group(models.Model):
            field = models.ManyToManyField('Person',
                through="AmbiguousRelationship", related_name='tertiary')

        class AmbiguousRelationship(models.Model):
            # Too much foreign keys to Person.
            first_person = models.ForeignKey(Person, related_name="first")
            second_person = models.ForeignKey(Person, related_name="second")
            second_model = models.ForeignKey(Group)

        field = Group._meta.get_field('field')
        errors = field.check(from_model=Group)
        expected = [
            Error(
                ("The model is used as an intermediate model by "
                 "'invalid_models_tests.Group.field', but it has more than one "
                 "foreign key to 'Person', which is ambiguous."),
                hint=('If you want to create a recursive relationship, use '
                      'ForeignKey("self", symmetrical=False, '
                      'through="AmbiguousRelationship").'),
                obj=field,
                id='fields.E335',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_relationship_model_with_foreign_key_to_wrong_model(self):
        class WrongModel(models.Model):
            pass

        class Person(models.Model):
            pass

        class Group(models.Model):
            members = models.ManyToManyField('Person',
                through="InvalidRelationship")

        class InvalidRelationship(models.Model):
            person = models.ForeignKey(Person)
            wrong_foreign_key = models.ForeignKey(WrongModel)
            # The last foreign key should point to Group model.

        field = Group._meta.get_field('members')
        errors = field.check(from_model=Group)
        expected = [
            Error(
                ("The model is used as an intermediate model by "
                 "'invalid_models_tests.Group.members', but it does not "
                 "have a foreign key to 'Group' or 'Person'."),
                hint=None,
                obj=InvalidRelationship,
                id='fields.E336',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_relationship_model_missing_foreign_key(self):
        class Person(models.Model):
            pass

        class Group(models.Model):
            members = models.ManyToManyField('Person',
                through="InvalidRelationship")

        class InvalidRelationship(models.Model):
            group = models.ForeignKey(Group)
            # No foreign key to Person

        field = Group._meta.get_field('members')
        errors = field.check(from_model=Group)
        expected = [
            Error(
                ("The model is used as an intermediate model by "
                 "'invalid_models_tests.Group.members', but it does not have "
                 "a foreign key to 'Group' or 'Person'."),
                hint=None,
                obj=InvalidRelationship,
                id='fields.E336',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_missing_relationship_model(self):
        class Person(models.Model):
            pass

        class Group(models.Model):
            members = models.ManyToManyField('Person',
                through="MissingM2MModel")

        field = Group._meta.get_field('members')
        errors = field.check(from_model=Group)
        expected = [
            Error(
                ("Field specifies a many-to-many relation through model "
                 "'MissingM2MModel', which has not been installed."),
                hint=None,
                obj=field,
                id='fields.E331',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_symmetrical_self_referential_field(self):
        class Person(models.Model):
            # Implicit symmetrical=False.
            friends = models.ManyToManyField('self', through="Relationship")

        class Relationship(models.Model):
            first = models.ForeignKey(Person, related_name="rel_from_set")
            second = models.ForeignKey(Person, related_name="rel_to_set")

        field = Person._meta.get_field('friends')
        errors = field.check(from_model=Person)
        expected = [
            Error(
                'Many-to-many fields with intermediate tables must not be symmetrical.',
                hint=None,
                obj=field,
                id='fields.E332',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_too_many_foreign_keys_in_self_referential_model(self):
        class Person(models.Model):
            friends = models.ManyToManyField('self',
                through="InvalidRelationship", symmetrical=False)

        class InvalidRelationship(models.Model):
            first = models.ForeignKey(Person, related_name="rel_from_set_2")
            second = models.ForeignKey(Person, related_name="rel_to_set_2")
            third = models.ForeignKey(Person, related_name="too_many_by_far")

        field = Person._meta.get_field('friends')
        errors = field.check(from_model=Person)
        expected = [
            Error(
                ("The model is used as an intermediate model by "
                 "'invalid_models_tests.Person.friends', but it has more than two "
                 "foreign keys to 'Person', which is ambiguous."),
                hint=None,
                obj=InvalidRelationship,
                id='fields.E333',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_symmetric_self_reference_with_intermediate_table(self):
        class Person(models.Model):
            # Explicit symmetrical=True.
            friends = models.ManyToManyField('self',
                through="Relationship", symmetrical=True)

        class Relationship(models.Model):
            first = models.ForeignKey(Person, related_name="rel_from_set")
            second = models.ForeignKey(Person, related_name="rel_to_set")

        field = Person._meta.get_field('friends')
        errors = field.check(from_model=Person)
        expected = [
            Error(
                'Many-to-many fields with intermediate tables must not be symmetrical.',
                hint=None,
                obj=field,
                id='fields.E332',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_foreign_key_to_abstract_model(self):
        class Model(models.Model):
            foreign_key = models.ForeignKey('AbstractModel')

        class AbstractModel(models.Model):
            class Meta:
                abstract = True

        field = Model._meta.get_field('foreign_key')
        errors = field.check()
        expected = [
            Error(
                ("Field defines a relation with model 'AbstractModel', "
                 "which is either not installed, or is abstract."),
                hint=None,
                obj=field,
                id='fields.E300',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_m2m_to_abstract_model(self):
        class AbstractModel(models.Model):
            class Meta:
                abstract = True

        class Model(models.Model):
            m2m = models.ManyToManyField('AbstractModel')

        field = Model._meta.get_field('m2m')
        errors = field.check(from_model=Model)
        expected = [
            Error(
                ("Field defines a relation with model 'AbstractModel', "
                 "which is either not installed, or is abstract."),
                hint=None,
                obj=field,
                id='fields.E300',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_unique_m2m(self):
        class Person(models.Model):
            name = models.CharField(max_length=5)

        class Group(models.Model):
            members = models.ManyToManyField('Person', unique=True)

        field = Group._meta.get_field('members')
        errors = field.check(from_model=Group)
        expected = [
            Error(
                'ManyToManyFields cannot be unique.',
                hint=None,
                obj=field,
                id='fields.E330',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_foreign_key_to_non_unique_field(self):
        class Target(models.Model):
            bad = models.IntegerField()  # No unique=True

        class Model(models.Model):
            foreign_key = models.ForeignKey('Target', to_field='bad')

        field = Model._meta.get_field('foreign_key')
        errors = field.check()
        expected = [
            Error(
                "'Target.bad' must set unique=True because it is referenced by a foreign key.",
                hint=None,
                obj=field,
                id='fields.E311',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_foreign_key_to_non_unique_field_under_explicit_model(self):
        class Target(models.Model):
            bad = models.IntegerField()

        class Model(models.Model):
            field = models.ForeignKey(Target, to_field='bad')

        field = Model._meta.get_field('field')
        errors = field.check()
        expected = [
            Error(
                "'Target.bad' must set unique=True because it is referenced by a foreign key.",
                hint=None,
                obj=field,
                id='fields.E311',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_foreign_object_to_non_unique_fields(self):
        class Person(models.Model):
            # Note that both fields are not unique.
            country_id = models.IntegerField()
            city_id = models.IntegerField()

        class MMembership(models.Model):
            person_country_id = models.IntegerField()
            person_city_id = models.IntegerField()

            person = models.ForeignObject(Person,
                from_fields=['person_country_id', 'person_city_id'],
                to_fields=['country_id', 'city_id'])

        field = MMembership._meta.get_field('person')
        errors = field.check()
        expected = [
            Error(
                ("None of the fields 'country_id', 'city_id' on model 'Person' "
                 "have a unique=True constraint."),
                hint=None,
                obj=field,
                id='fields.E310',
            )
        ]
        self.assertEqual(errors, expected)

    def test_on_delete_set_null_on_non_nullable_field(self):
        class Person(models.Model):
            pass

        class Model(models.Model):
            foreign_key = models.ForeignKey('Person',
                on_delete=models.SET_NULL)

        field = Model._meta.get_field('foreign_key')
        errors = field.check()
        expected = [
            Error(
                'Field specifies on_delete=SET_NULL, but cannot be null.',
                hint='Set null=True argument on the field, or change the on_delete rule.',
                obj=field,
                id='fields.E320',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_on_delete_set_default_without_default_value(self):
        class Person(models.Model):
            pass

        class Model(models.Model):
            foreign_key = models.ForeignKey('Person',
                on_delete=models.SET_DEFAULT)

        field = Model._meta.get_field('foreign_key')
        errors = field.check()
        expected = [
            Error(
                'Field specifies on_delete=SET_DEFAULT, but has no default value.',
                hint='Set a default value, or change the on_delete rule.',
                obj=field,
                id='fields.E321',
            ),
        ]
        self.assertEqual(errors, expected)

    @skipIfDBFeature('interprets_empty_strings_as_nulls')
    def test_nullable_primary_key(self):
        class Model(models.Model):
            field = models.IntegerField(primary_key=True, null=True)

        field = Model._meta.get_field('field')
        errors = field.check()
        expected = [
            Error(
                'Primary keys must not have null=True.',
                hint='Set null=False on the field, or remove primary_key=True argument.',
                obj=field,
                id='fields.E007',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_not_swapped_model(self):
        class SwappableModel(models.Model):
            # A model that can be, but isn't swapped out. References to this
            # model should *not* raise any validation error.
            class Meta:
                swappable = 'TEST_SWAPPABLE_MODEL'

        class Model(models.Model):
            explicit_fk = models.ForeignKey(SwappableModel,
                related_name='explicit_fk')
            implicit_fk = models.ForeignKey('invalid_models_tests.SwappableModel',
                related_name='implicit_fk')
            explicit_m2m = models.ManyToManyField(SwappableModel,
                related_name='explicit_m2m')
            implicit_m2m = models.ManyToManyField(
                'invalid_models_tests.SwappableModel',
                related_name='implicit_m2m')

        explicit_fk = Model._meta.get_field('explicit_fk')
        self.assertEqual(explicit_fk.check(), [])

        implicit_fk = Model._meta.get_field('implicit_fk')
        self.assertEqual(implicit_fk.check(), [])

        explicit_m2m = Model._meta.get_field('explicit_m2m')
        self.assertEqual(explicit_m2m.check(from_model=Model), [])

        implicit_m2m = Model._meta.get_field('implicit_m2m')
        self.assertEqual(implicit_m2m.check(from_model=Model), [])

    @override_settings(TEST_SWAPPED_MODEL='invalid_models_tests.Replacement')
    def test_referencing_to_swapped_model(self):
        class Replacement(models.Model):
            pass

        class SwappedModel(models.Model):
            class Meta:
                swappable = 'TEST_SWAPPED_MODEL'

        class Model(models.Model):
            explicit_fk = models.ForeignKey(SwappedModel,
                related_name='explicit_fk')
            implicit_fk = models.ForeignKey('invalid_models_tests.SwappedModel',
                related_name='implicit_fk')
            explicit_m2m = models.ManyToManyField(SwappedModel,
                related_name='explicit_m2m')
            implicit_m2m = models.ManyToManyField(
                'invalid_models_tests.SwappedModel',
                related_name='implicit_m2m')

        fields = [
            Model._meta.get_field('explicit_fk'),
            Model._meta.get_field('implicit_fk'),
            Model._meta.get_field('explicit_m2m'),
            Model._meta.get_field('implicit_m2m'),
        ]

        expected_error = Error(
            ("Field defines a relation with the model "
             "'invalid_models_tests.SwappedModel', which has been swapped out."),
            hint="Update the relation to point at 'settings.TEST_SWAPPED_MODEL'.",
            id='fields.E301',
        )

        for field in fields:
            expected_error.obj = field
            errors = field.check(from_model=Model)
            self.assertEqual(errors, [expected_error])


class AccessorClashTests(IsolatedModelsTestCase):

    def test_fk_to_integer(self):
        self._test_accessor_clash(
            target=models.IntegerField(),
            relative=models.ForeignKey('Target'))

    def test_fk_to_fk(self):
        self._test_accessor_clash(
            target=models.ForeignKey('Another'),
            relative=models.ForeignKey('Target'))

    def test_fk_to_m2m(self):
        self._test_accessor_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ForeignKey('Target'))

    def test_m2m_to_integer(self):
        self._test_accessor_clash(
            target=models.IntegerField(),
            relative=models.ManyToManyField('Target'))

    def test_m2m_to_fk(self):
        self._test_accessor_clash(
            target=models.ForeignKey('Another'),
            relative=models.ManyToManyField('Target'))

    def test_m2m_to_m2m(self):
        self._test_accessor_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ManyToManyField('Target'))

    def _test_accessor_clash(self, target, relative):
        class Another(models.Model):
            pass

        class Target(models.Model):
            model_set = target

        class Model(models.Model):
            rel = relative

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.rel' clashes with field name 'Target.model_set'.",
                hint=("Rename field 'Target.model_set', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.rel'."),
                obj=Model._meta.get_field('rel'),
                id='fields.E302',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_clash_between_accessors(self):
        class Target(models.Model):
            pass

        class Model(models.Model):
            foreign = models.ForeignKey(Target)
            m2m = models.ManyToManyField(Target)

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.foreign' clashes with reverse accessor for 'Model.m2m'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.foreign' or 'Model.m2m'."),
                obj=Model._meta.get_field('foreign'),
                id='fields.E304',
            ),
            Error(
                "Reverse accessor for 'Model.m2m' clashes with reverse accessor for 'Model.foreign'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.m2m' or 'Model.foreign'."),
                obj=Model._meta.get_field('m2m'),
                id='fields.E304',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_m2m_to_m2m_with_inheritance(self):
        """ Ref #22047. """

        class Target(models.Model):
            pass

        class Model(models.Model):
            children = models.ManyToManyField('Child',
                related_name="m2m_clash", related_query_name="no_clash")

        class Parent(models.Model):
            m2m_clash = models.ManyToManyField('Target')

        class Child(Parent):
            pass

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.children' clashes with field name 'Child.m2m_clash'.",
                hint=("Rename field 'Child.m2m_clash', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.children'."),
                obj=Model._meta.get_field('children'),
                id='fields.E302',
            )
        ]
        self.assertEqual(errors, expected)


class ReverseQueryNameClashTests(IsolatedModelsTestCase):

    def test_fk_to_integer(self):
        self._test_reverse_query_name_clash(
            target=models.IntegerField(),
            relative=models.ForeignKey('Target'))

    def test_fk_to_fk(self):
        self._test_reverse_query_name_clash(
            target=models.ForeignKey('Another'),
            relative=models.ForeignKey('Target'))

    def test_fk_to_m2m(self):
        self._test_reverse_query_name_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ForeignKey('Target'))

    def test_m2m_to_integer(self):
        self._test_reverse_query_name_clash(
            target=models.IntegerField(),
            relative=models.ManyToManyField('Target'))

    def test_m2m_to_fk(self):
        self._test_reverse_query_name_clash(
            target=models.ForeignKey('Another'),
            relative=models.ManyToManyField('Target'))

    def test_m2m_to_m2m(self):
        self._test_reverse_query_name_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ManyToManyField('Target'))

    def _test_reverse_query_name_clash(self, target, relative):
        class Another(models.Model):
            pass

        class Target(models.Model):
            model = target

        class Model(models.Model):
            rel = relative

        errors = Model.check()
        expected = [
            Error(
                "Reverse query name for 'Model.rel' clashes with field name 'Target.model'.",
                hint=("Rename field 'Target.model', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.rel'."),
                obj=Model._meta.get_field('rel'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)


class ExplicitRelatedNameClashTests(IsolatedModelsTestCase):

    def test_fk_to_integer(self):
        self._test_explicit_related_name_clash(
            target=models.IntegerField(),
            relative=models.ForeignKey('Target', related_name='clash'))

    def test_fk_to_fk(self):
        self._test_explicit_related_name_clash(
            target=models.ForeignKey('Another'),
            relative=models.ForeignKey('Target', related_name='clash'))

    def test_fk_to_m2m(self):
        self._test_explicit_related_name_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ForeignKey('Target', related_name='clash'))

    def test_m2m_to_integer(self):
        self._test_explicit_related_name_clash(
            target=models.IntegerField(),
            relative=models.ManyToManyField('Target', related_name='clash'))

    def test_m2m_to_fk(self):
        self._test_explicit_related_name_clash(
            target=models.ForeignKey('Another'),
            relative=models.ManyToManyField('Target', related_name='clash'))

    def test_m2m_to_m2m(self):
        self._test_explicit_related_name_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ManyToManyField('Target', related_name='clash'))

    def _test_explicit_related_name_clash(self, target, relative):
        class Another(models.Model):
            pass

        class Target(models.Model):
            clash = target

        class Model(models.Model):
            rel = relative

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.rel' clashes with field name 'Target.clash'.",
                hint=("Rename field 'Target.clash', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.rel'."),
                obj=Model._meta.get_field('rel'),
                id='fields.E302',
            ),
            Error(
                "Reverse query name for 'Model.rel' clashes with field name 'Target.clash'.",
                hint=("Rename field 'Target.clash', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.rel'."),
                obj=Model._meta.get_field('rel'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)


class ExplicitRelatedQueryNameClashTests(IsolatedModelsTestCase):

    def test_fk_to_integer(self):
        self._test_explicit_related_query_name_clash(
            target=models.IntegerField(),
            relative=models.ForeignKey('Target',
                related_query_name='clash'))

    def test_fk_to_fk(self):
        self._test_explicit_related_query_name_clash(
            target=models.ForeignKey('Another'),
            relative=models.ForeignKey('Target',
                related_query_name='clash'))

    def test_fk_to_m2m(self):
        self._test_explicit_related_query_name_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ForeignKey('Target',
                related_query_name='clash'))

    def test_m2m_to_integer(self):
        self._test_explicit_related_query_name_clash(
            target=models.IntegerField(),
            relative=models.ManyToManyField('Target',
                related_query_name='clash'))

    def test_m2m_to_fk(self):
        self._test_explicit_related_query_name_clash(
            target=models.ForeignKey('Another'),
            relative=models.ManyToManyField('Target',
                related_query_name='clash'))

    def test_m2m_to_m2m(self):
        self._test_explicit_related_query_name_clash(
            target=models.ManyToManyField('Another'),
            relative=models.ManyToManyField('Target',
                related_query_name='clash'))

    def _test_explicit_related_query_name_clash(self, target, relative):
        class Another(models.Model):
            pass

        class Target(models.Model):
            clash = target

        class Model(models.Model):
            rel = relative

        errors = Model.check()
        expected = [
            Error(
                "Reverse query name for 'Model.rel' clashes with field name 'Target.clash'.",
                hint=("Rename field 'Target.clash', or add/change a related_name "
                      "argument to the definition for field 'Model.rel'."),
                obj=Model._meta.get_field('rel'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)


class SelfReferentialM2MClashTests(IsolatedModelsTestCase):

    def test_clash_between_accessors(self):
        class Model(models.Model):
            first_m2m = models.ManyToManyField('self', symmetrical=False)
            second_m2m = models.ManyToManyField('self', symmetrical=False)

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.first_m2m' clashes with reverse accessor for 'Model.second_m2m'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.first_m2m' or 'Model.second_m2m'."),
                obj=Model._meta.get_field('first_m2m'),
                id='fields.E304',
            ),
            Error(
                "Reverse accessor for 'Model.second_m2m' clashes with reverse accessor for 'Model.first_m2m'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.second_m2m' or 'Model.first_m2m'."),
                obj=Model._meta.get_field('second_m2m'),
                id='fields.E304',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_accessor_clash(self):
        class Model(models.Model):
            model_set = models.ManyToManyField("self", symmetrical=False)

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.model_set' clashes with field name 'Model.model_set'.",
                hint=("Rename field 'Model.model_set', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.model_set'."),
                obj=Model._meta.get_field('model_set'),
                id='fields.E302',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_reverse_query_name_clash(self):
        class Model(models.Model):
            model = models.ManyToManyField("self", symmetrical=False)

        errors = Model.check()
        expected = [
            Error(
                "Reverse query name for 'Model.model' clashes with field name 'Model.model'.",
                hint=("Rename field 'Model.model', or add/change a related_name "
                      "argument to the definition for field 'Model.model'."),
                obj=Model._meta.get_field('model'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_clash_under_explicit_related_name(self):
        class Model(models.Model):
            clash = models.IntegerField()
            m2m = models.ManyToManyField("self",
                symmetrical=False, related_name='clash')

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.m2m' clashes with field name 'Model.clash'.",
                hint=("Rename field 'Model.clash', or add/change a related_name "
                      "argument to the definition for field 'Model.m2m'."),
                obj=Model._meta.get_field('m2m'),
                id='fields.E302',
            ),
            Error(
                "Reverse query name for 'Model.m2m' clashes with field name 'Model.clash'.",
                hint=("Rename field 'Model.clash', or add/change a related_name "
                      "argument to the definition for field 'Model.m2m'."),
                obj=Model._meta.get_field('m2m'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_valid_model(self):
        class Model(models.Model):
            first = models.ManyToManyField("self",
                symmetrical=False, related_name='first_accessor')
            second = models.ManyToManyField("self",
                symmetrical=False, related_name='second_accessor')

        errors = Model.check()
        self.assertEqual(errors, [])


class SelfReferentialFKClashTests(IsolatedModelsTestCase):

    def test_accessor_clash(self):
        class Model(models.Model):
            model_set = models.ForeignKey("Model")

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.model_set' clashes with field name 'Model.model_set'.",
                hint=("Rename field 'Model.model_set', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.model_set'."),
                obj=Model._meta.get_field('model_set'),
                id='fields.E302',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_reverse_query_name_clash(self):
        class Model(models.Model):
            model = models.ForeignKey("Model")

        errors = Model.check()
        expected = [
            Error(
                "Reverse query name for 'Model.model' clashes with field name 'Model.model'.",
                hint=("Rename field 'Model.model', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.model'."),
                obj=Model._meta.get_field('model'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)

    def test_clash_under_explicit_related_name(self):
        class Model(models.Model):
            clash = models.CharField(max_length=10)
            foreign = models.ForeignKey("Model", related_name='clash')

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.foreign' clashes with field name 'Model.clash'.",
                hint=("Rename field 'Model.clash', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.foreign'."),
                obj=Model._meta.get_field('foreign'),
                id='fields.E302',
            ),
            Error(
                "Reverse query name for 'Model.foreign' clashes with field name 'Model.clash'.",
                hint=("Rename field 'Model.clash', or add/change "
                      "a related_name argument to the definition "
                      "for field 'Model.foreign'."),
                obj=Model._meta.get_field('foreign'),
                id='fields.E303',
            ),
        ]
        self.assertEqual(errors, expected)


class ComplexClashTests(IsolatedModelsTestCase):

    # New tests should not be included here, because this is a single,
    # self-contained sanity check, not a test of everything.
    def test_complex_clash(self):
        class Target(models.Model):
            tgt_safe = models.CharField(max_length=10)
            clash = models.CharField(max_length=10)
            model = models.CharField(max_length=10)

            clash1_set = models.CharField(max_length=10)

        class Model(models.Model):
            src_safe = models.CharField(max_length=10)

            foreign_1 = models.ForeignKey(Target, related_name='id')
            foreign_2 = models.ForeignKey(Target, related_name='src_safe')

            m2m_1 = models.ManyToManyField(Target, related_name='id')
            m2m_2 = models.ManyToManyField(Target, related_name='src_safe')

        errors = Model.check()
        expected = [
            Error(
                "Reverse accessor for 'Model.foreign_1' clashes with field name 'Target.id'.",
                hint=("Rename field 'Target.id', or add/change a related_name "
                      "argument to the definition for field 'Model.foreign_1'."),
                obj=Model._meta.get_field('foreign_1'),
                id='fields.E302',
            ),
            Error(
                "Reverse query name for 'Model.foreign_1' clashes with field name 'Target.id'.",
                hint=("Rename field 'Target.id', or add/change a related_name "
                      "argument to the definition for field 'Model.foreign_1'."),
                obj=Model._meta.get_field('foreign_1'),
                id='fields.E303',
            ),
            Error(
                "Reverse accessor for 'Model.foreign_1' clashes with reverse accessor for 'Model.m2m_1'.",
                hint=("Add or change a related_name argument to "
                      "the definition for 'Model.foreign_1' or 'Model.m2m_1'."),
                obj=Model._meta.get_field('foreign_1'),
                id='fields.E304',
            ),
            Error(
                "Reverse query name for 'Model.foreign_1' clashes with reverse query name for 'Model.m2m_1'.",
                hint=("Add or change a related_name argument to "
                      "the definition for 'Model.foreign_1' or 'Model.m2m_1'."),
                obj=Model._meta.get_field('foreign_1'),
                id='fields.E305',
            ),

            Error(
                "Reverse accessor for 'Model.foreign_2' clashes with reverse accessor for 'Model.m2m_2'.",
                hint=("Add or change a related_name argument "
                      "to the definition for 'Model.foreign_2' or 'Model.m2m_2'."),
                obj=Model._meta.get_field('foreign_2'),
                id='fields.E304',
            ),
            Error(
                "Reverse query name for 'Model.foreign_2' clashes with reverse query name for 'Model.m2m_2'.",
                hint=("Add or change a related_name argument to "
                      "the definition for 'Model.foreign_2' or 'Model.m2m_2'."),
                obj=Model._meta.get_field('foreign_2'),
                id='fields.E305',
            ),

            Error(
                "Reverse accessor for 'Model.m2m_1' clashes with field name 'Target.id'.",
                hint=("Rename field 'Target.id', or add/change a related_name "
                      "argument to the definition for field 'Model.m2m_1'."),
                obj=Model._meta.get_field('m2m_1'),
                id='fields.E302',
            ),
            Error(
                "Reverse query name for 'Model.m2m_1' clashes with field name 'Target.id'.",
                hint=("Rename field 'Target.id', or add/change a related_name "
                      "argument to the definition for field 'Model.m2m_1'."),
                obj=Model._meta.get_field('m2m_1'),
                id='fields.E303',
            ),
            Error(
                "Reverse accessor for 'Model.m2m_1' clashes with reverse accessor for 'Model.foreign_1'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.m2m_1' or 'Model.foreign_1'."),
                obj=Model._meta.get_field('m2m_1'),
                id='fields.E304',
            ),
            Error(
                "Reverse query name for 'Model.m2m_1' clashes with reverse query name for 'Model.foreign_1'.",
                hint=("Add or change a related_name argument to "
                      "the definition for 'Model.m2m_1' or 'Model.foreign_1'."),
                obj=Model._meta.get_field('m2m_1'),
                id='fields.E305',
            ),

            Error(
                "Reverse accessor for 'Model.m2m_2' clashes with reverse accessor for 'Model.foreign_2'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.m2m_2' or 'Model.foreign_2'."),
                obj=Model._meta.get_field('m2m_2'),
                id='fields.E304',
            ),
            Error(
                "Reverse query name for 'Model.m2m_2' clashes with reverse query name for 'Model.foreign_2'.",
                hint=("Add or change a related_name argument to the definition "
                      "for 'Model.m2m_2' or 'Model.foreign_2'."),
                obj=Model._meta.get_field('m2m_2'),
                id='fields.E305',
            ),
        ]
        self.assertEqual(errors, expected)
