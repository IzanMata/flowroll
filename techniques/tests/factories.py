import factory
from factory.django import DjangoModelFactory
import random

from techniques.models import TechniqueCategory, Technique, TechniqueVariation, TechniqueFlow, TechniqueVideo
from core.models import Belt
from core.seeders.utils import BJJ_TECHNIQUE_NAMES


class TechniqueCategoryFactory(DjangoModelFactory):
    class Meta:
        model = TechniqueCategory

    name = factory.Iterator([
        "Guard", "Submissions", "Takedowns", "Escapes",
        "Sweeps", "Passing", "Back Attacks", "Leg Locks"
    ])
    description = factory.LazyAttribute(
        lambda obj: f"Techniques focused on {obj.name.lower()} in Brazilian Jiu-Jitsu"
    )


class TechniqueFactory(DjangoModelFactory):
    class Meta:
        model = Technique

    name = factory.Iterator(BJJ_TECHNIQUE_NAMES)
    description = factory.LazyAttribute(
        lambda obj: f"Detailed breakdown of {obj.name} technique execution and variations"
    )
    difficulty = factory.LazyAttribute(lambda obj: random.randint(1, 5))
    min_belt = factory.LazyAttribute(
        lambda obj: random.choice([Belt.BeltColor.WHITE, Belt.BeltColor.BLUE, Belt.BeltColor.PURPLE, Belt.BeltColor.BROWN, Belt.BeltColor.BLACK])
    )

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for category in extracted:
                self.categories.add(category)
        else:
            # Add 1-2 random categories
            from techniques.models import TechniqueCategory
            categories = list(TechniqueCategory.objects.all())
            if categories:
                selected = random.sample(categories, random.randint(1, min(2, len(categories))))
                self.categories.add(*selected)


class TechniqueVideoFactory(DjangoModelFactory):
    class Meta:
        model = TechniqueVideo

    technique = factory.SubFactory(TechniqueFactory)
    title = factory.LazyAttribute(
        lambda obj: f"{obj.technique.name} - Tutorial"
    )
    url = factory.LazyAttribute(
        lambda obj: f"https://youtube.com/watch?v={factory.fuzzy.FuzzyText(length=11).fuzz()}"
    )
    source = "YouTube"


class TechniqueVariationFactory(DjangoModelFactory):
    class Meta:
        model = TechniqueVariation

    technique = factory.SubFactory(TechniqueFactory)
    name = factory.LazyAttribute(
        lambda obj: f"{obj.technique.name} - {random.choice(['Setup', 'Finish', 'Counter', 'Entry'])}"
    )
    description = factory.LazyAttribute(
        lambda obj: f"Alternative execution of {obj.technique.name} focusing on {obj.name.split(' - ')[1].lower()}"
    )


class TechniqueFlowFactory(DjangoModelFactory):
    class Meta:
        model = TechniqueFlow

    from_technique = factory.SubFactory(TechniqueFactory)
    to_technique = factory.SubFactory(TechniqueFactory)
    transition_type = factory.LazyAttribute(
        lambda obj: random.choice(['chain', 'counter', 'escape', 'setup'])
    )
    description = factory.LazyAttribute(
        lambda obj: f"Transition from {obj.from_technique.name} to {obj.to_technique.name}"
    )