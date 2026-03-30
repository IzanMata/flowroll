from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("techniques", "0005_techniquevideo_updated_at_alter_technique_created_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="technique",
            name="difficulty",
            field=models.PositiveSmallIntegerField(
                choices=[(1, "1 Star"), (2, "2 Stars"), (3, "3 Stars"), (4, "4 Stars"), (5, "5 Stars")],
                default=1,
            ),
        ),
    ]
