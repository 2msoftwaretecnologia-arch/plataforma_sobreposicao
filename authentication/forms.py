from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import UserProfile


class RegisterForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('autocomplete', 'off')
        self.fields['username'].widget.attrs['autofocus'] = True
        self.fields['username'].help_text = None
        self.fields['password1'].help_text = 'Mínimo de 8 caracteres. Não pode ser inteiramente numérica.'
        self.fields['password2'].help_text = None


class OnboardingForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ('objetivo', 'objetivo_outro', 'profissao', 'profissao_outro')
        widgets = {
            'objetivo': forms.RadioSelect,
            'profissao': forms.Select,
        }

    def clean(self):
        cleaned_data = super().clean()
        objetivo = cleaned_data.get('objetivo')
        objetivo_outro = cleaned_data.get('objetivo_outro', '').strip()
        profissao = cleaned_data.get('profissao')
        profissao_outro = cleaned_data.get('profissao_outro', '').strip()

        if objetivo == UserProfile.OBJETIVO_OUTRO and not objetivo_outro:
            self.add_error('objetivo_outro', 'Conte pra gente qual é o seu objetivo.')

        if profissao == UserProfile.PROFISSAO_OUTRO and not profissao_outro:
            self.add_error('profissao_outro', 'Conte pra gente qual é a sua profissão.')

        return cleaned_data
