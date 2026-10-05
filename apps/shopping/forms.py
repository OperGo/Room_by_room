from django import forms

from apps.projects.models import Project, Task

from .models import ShoppingItem


class ShoppingItemForm(forms.ModelForm):
    version = forms.IntegerField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = ShoppingItem
        fields = ["description", "quantity", "unit", "project", "task", "retailer", "notes"]
        labels = {"project": "Project", "task": "Task", "retailer": "Preferred retailer"}
        widgets = {
            "quantity": forms.NumberInput(attrs={"step": "any", "min": "0.01", "inputmode": "decimal"}),
            "unit": forms.TextInput(attrs={"placeholder": "e.g. tins"}),
        }

    def __init__(self, owner, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner
        self.fields["project"].queryset = Project.objects.for_owner(owner).exclude(status=Project.Status.ARCHIVED).order_by("title")
        self.fields["project"].empty_label = "Shared / no project"
        self.fields["task"].empty_label = "Not linked to a task"
        self.fields["task"].queryset = Task.objects.for_owner(owner).filter(
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
        ).select_related("project").order_by("project__title", "position")
        self.fields["task"].label_from_instance = lambda t: f"{t.project.title} · {t.title}"
        if self.instance.pk:
            self.fields["version"].initial = self.instance.version

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity is None or quantity <= 0:
            raise forms.ValidationError("Quantity must be more than zero.")
        return quantity

    def clean(self):
        data = super().clean()
        task, project = data.get("task"), data.get("project")
        if task and project and task.project_id != project.pk:
            self.add_error("task", "That task belongs to a different project.")
        if task and not project:
            data["project"] = task.project
        return data
