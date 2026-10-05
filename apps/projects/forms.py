from django import forms

from .models import Project, Task

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class ProjectForm(forms.ModelForm):
    version = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Project
        fields = ["title", "room", "status", "budget", "start_date", "completion_date", "notes"]
        labels = {"budget": "Budget (£)", "completion_date": "Completion date", "room": "Room"}
        widgets = {
            "start_date": DATE,
            "completion_date": DATE,
            "notes": forms.Textarea(attrs={"rows": 4}),
            "budget": forms.NumberInput(attrs={"step": "0.01", "min": "0", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["version"].initial = self.instance.version
            # Status changes with side effects (completion warnings) use their own action.
            self.fields.pop("status")

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("completion_date")
        if start and end and end < start:
            self.add_error("completion_date", "Completion cannot be before the start date.")
        return data


class TaskForm(forms.ModelForm):
    version = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Task
        fields = ["title", "estimated_minutes", "due_date", "notes"]
        labels = {"estimated_minutes": "Estimated minutes", "due_date": "Due date"}
        widgets = {
            "due_date": DATE,
            "notes": forms.Textarea(attrs={"rows": 3}),
            "estimated_minutes": forms.NumberInput(attrs={"min": "1", "inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["version"].initial = self.instance.version


class DependencyForm(forms.Form):
    prerequisites = forms.ModelMultipleChoiceField(
        queryset=Task.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
        label="This task waits for",
    )

    def __init__(self, task, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["prerequisites"].queryset = task.project.tasks.exclude(pk=task.pk)
        self.fields["prerequisites"].initial = list(task.prerequisites().values_list("pk", flat=True))


class PhotoForm(forms.Form):
    photo = forms.FileField(label="Photo", widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/heic,image/heif"}))
    caption = forms.CharField(max_length=200, required=False)


class ProjectSearchForm(forms.Form):
    q = forms.CharField(required=False, label="Search projects")
    status = forms.ChoiceField(required=False, choices=[("", "All statuses")] + list(Project.Status.choices))
