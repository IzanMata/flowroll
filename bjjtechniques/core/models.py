from django.db import models

class Belt(models.Model):
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=50)
    rank = models.PositiveIntegerField()  # 1 = white, 2 = blue, etc.

    def __str__(self):
        return self.name

class Technique(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    video_url = models.URLField(null=True, blank=True)
    belt = models.ForeignKey(Belt, related_name="techniques", on_delete=models.CASCADE)
    category = models.CharField(max_length=100, choices=[
        ('Guard', 'Guard'),
        ('Sweep', 'Sweep'),
        ('Submission', 'Submission'),
        ('Transition', 'Transition'),
    ])

    def __str__(self):
        return self.name

class Transition(models.Model):
    from_technique = models.ForeignKey(Technique, related_name="from_transitions", on_delete=models.CASCADE)
    to_technique = models.ForeignKey(Technique, related_name="to_transitions", on_delete=models.CASCADE)
    description = models.TextField()

    def __str__(self):
        return f"{self.from_technique} -> {self.to_technique}"

class Finalization(models.Model):
    technique = models.ForeignKey(Technique, related_name="finalizations", on_delete=models.CASCADE)
    submission_type = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return f"{self.submission_type} from {self.technique}"