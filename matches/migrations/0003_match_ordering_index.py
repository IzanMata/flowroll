from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0002_match_academy"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="match",
            options={"ordering": ["-date"]},
        ),
        migrations.AddIndex(
            model_name="match",
            index=models.Index(
                fields=["academy", "is_finished"],
                name="match_academy_finished_idx",
            ),
        ),
    ]
