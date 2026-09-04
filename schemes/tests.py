from django.test import Client, TestCase
from django.urls import reverse

from .models import Scheme, Tag
from .views import FAVORITE_SCHEMES_SESSION_KEY


class SchemeModelTests(TestCase):
    """Тести моделей бібліотеки схем."""

    def setUp(self) -> None:
        self.tag = Tag.objects.create(
            name="квіти",
        )

        self.scheme = Scheme.objects.create(
            title="Браслет із ромашками",
            source=Scheme.Source.OWN,
            category=Scheme.Category.JEWELRY,
            subcategory="Браслети",
            author="Yevheniia",
            difficulty=Scheme.Difficulty.BEGINNER,
            status=Scheme.Status.PLANNED,
            description="Тестова схема браслета",
        )

        self.scheme.tags.add(
            self.tag
        )

    def test_scheme_string_representation(
        self,
    ) -> None:
        """Модель Scheme повертає назву схеми."""

        self.assertEqual(
            str(self.scheme),
            "Браслет із ромашками",
        )

    def test_tag_string_representation(
        self,
    ) -> None:
        """Модель Tag повертає назву тегу."""

        self.assertEqual(
            str(self.tag),
            "квіти",
        )

    def test_scheme_has_tag(
        self,
    ) -> None:
        """До схеми можна прив’язати тег."""

        self.assertIn(
            self.tag,
            self.scheme.tags.all(),
        )

    def test_default_scheme_status(
        self,
    ) -> None:
        """
        Нова схема за замовчуванням
        має статус «Планую».
        """

        scheme = Scheme.objects.create(
            title="Нова схема",
            source=Scheme.Source.FREE,
            category=Scheme.Category.OTHER,
        )

        self.assertEqual(
            scheme.status,
            Scheme.Status.PLANNED,
        )

    def test_default_scheme_visibility(
        self,
    ) -> None:
        """
        Нова схема за замовчуванням
        є загальнодоступною.
        """

        scheme = Scheme.objects.create(
            title="Загальнодоступна схема",
            source=Scheme.Source.FREE,
            category=Scheme.Category.OTHER,
        )

        self.assertEqual(
            scheme.visibility,
            Scheme.Visibility.PUBLIC,
        )

    def test_scheme_without_owner_is_allowed(
        self,
    ) -> None:
        """
        Загальна схема може не мати
        персонального власника.
        """

        self.assertIsNone(
            self.scheme.owner
        )


class SchemeViewTests(TestCase):
    """Тести сторінок бібліотеки схем."""

    def setUp(self) -> None:
        self.flowers_tag = Tag.objects.create(
            name="квіти",
        )

        self.gift_tag = Tag.objects.create(
            name="подарунок",
        )

        self.scheme = Scheme.objects.create(
            title="Браслет із ромашками",
            source=Scheme.Source.OWN,
            category=Scheme.Category.JEWELRY,
            subcategory="Браслети",
            author="Yevheniia",
            difficulty=Scheme.Difficulty.BEGINNER,
            status=Scheme.Status.PLANNED,
            visibility=Scheme.Visibility.PUBLIC,
            description=(
                "Квітковий браслет із бісеру"
            ),
        )

        self.scheme.tags.add(
            self.flowers_tag
        )

        self.other_scheme = Scheme.objects.create(
            title="Міфічна білочка",
            source=Scheme.Source.FREE,
            category=Scheme.Category.TOYS,
            author="Майстер",
            difficulty=(
                Scheme.Difficulty.INTERMEDIATE
            ),
            status=Scheme.Status.COMPLETED,
            visibility=Scheme.Visibility.PUBLIC,
            description=(
                "Маленька іграшка з бісеру"
            ),
        )

        self.other_scheme.tags.add(
            self.gift_tag
        )

        self.private_scheme = Scheme.objects.create(
            title="Приватна тестова схема",
            source=Scheme.Source.OWN,
            category=Scheme.Category.OTHER,
            status=Scheme.Status.PLANNED,
            visibility=Scheme.Visibility.PRIVATE,
            description="Приватний опис",
        )

    def get_form_data(
        self,
        **overrides: object,
    ) -> dict[str, object]:
        """Повертає правильні тестові дані форми."""

        data: dict[str, object] = {
            "title": "Нова тестова схема",
            "source": Scheme.Source.OWN,
            "category": Scheme.Category.JEWELRY,
            "subcategory": "Кольє",
            "author": "Yevheniia",
            "difficulty": (
                Scheme.Difficulty.BEGINNER
            ),
            "status": Scheme.Status.PLANNED,
            "tags": [
                str(self.flowers_tag.pk)
            ],
            "description": (
                "Опис нової тестової схеми"
            ),
        }

        data.update(
            overrides
        )

        return data

    def test_scheme_list_page(
        self,
    ) -> None:
        """Каталог схем відкривається."""

        response = self.client.get(
            reverse(
                "schemes:scheme_list"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "schemes/scheme_list.html",
        )

        self.assertContains(
            response,
            "Браслет із ромашками",
        )

        self.assertContains(
            response,
            "Міфічна білочка",
        )

    def test_private_scheme_is_hidden_from_list(
        self,
    ) -> None:
        """Приватна схема не показується в каталозі."""

        response = self.client.get(
            reverse(
                "schemes:scheme_list"
            )
        )

        self.assertNotContains(
            response,
            "Приватна тестова схема",
        )

    def test_scheme_search_by_title(
        self,
    ) -> None:
        """Пошук знаходить схему за назвою."""

        response = self.client.get(
            reverse(
                "schemes:scheme_list"
            ),
            {
                "q": "ромашками",
            },
        )

        self.assertContains(
            response,
            "Браслет із ромашками",
        )

        self.assertNotContains(
            response,
            "Міфічна білочка",
        )

    def test_scheme_search_by_tag(
        self,
    ) -> None:
        """Пошук знаходить схему за тегом."""

        response = self.client.get(
            reverse(
                "schemes:scheme_list"
            ),
            {
                "q": "подарунок",
            },
        )

        self.assertContains(
            response,
            "Міфічна білочка",
        )

        self.assertNotContains(
            response,
            "Браслет із ромашками",
        )

    def test_scheme_filter_by_category(
        self,
    ) -> None:
        """Каталог фільтрується за категорією."""

        response = self.client.get(
            reverse(
                "schemes:scheme_list"
            ),
            {
                "category": (
                    Scheme.Category.JEWELRY
                ),
            },
        )

        self.assertContains(
            response,
            "Браслет із ромашками",
        )

        self.assertNotContains(
            response,
            "Міфічна білочка",
        )

    def test_scheme_filter_by_status(
        self,
    ) -> None:
        """Каталог фільтрується за статусом."""

        response = self.client.get(
            reverse(
                "schemes:scheme_list"
            ),
            {
                "status": (
                    Scheme.Status.COMPLETED
                ),
            },
        )

        self.assertContains(
            response,
            "Міфічна білочка",
        )

        self.assertNotContains(
            response,
            "Браслет із ромашками",
        )

    def test_scheme_detail_page(
        self,
    ) -> None:
        """Детальна картка схеми відкривається."""

        response = self.client.get(
            reverse(
                "schemes:scheme_detail",
                kwargs={
                    "pk": self.scheme.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "schemes/scheme_detail.html",
        )

        self.assertContains(
            response,
            "Браслет із ромашками",
        )

        self.assertContains(
            response,
            "Квітковий браслет із бісеру",
        )

    def test_private_scheme_detail_returns_404(
        self,
    ) -> None:
        """
        Детальна сторінка приватної схеми
        недоступна на публічному сайті.
        """

        response = self.client.get(
            reverse(
                "schemes:scheme_detail",
                kwargs={
                    "pk": self.private_scheme.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_missing_scheme_returns_404(
        self,
    ) -> None:
        """Неіснуюча схема повертає помилку 404."""

        response = self.client.get(
            reverse(
                "schemes:scheme_detail",
                kwargs={
                    "pk": 99999,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_scheme_create(
        self,
    ) -> None:
        """Нову схему можна створити через форму."""

        response = self.client.post(
            reverse(
                "schemes:scheme_create"
            ),
            data=self.get_form_data(),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        created_scheme = Scheme.objects.get(
            title="Нова тестова схема"
        )

        self.assertEqual(
            created_scheme.category,
            Scheme.Category.JEWELRY,
        )

        self.assertEqual(
            created_scheme.visibility,
            Scheme.Visibility.PUBLIC,
        )

        self.assertIsNone(
            created_scheme.owner
        )

        self.assertIn(
            self.flowers_tag,
            created_scheme.tags.all(),
        )

        self.assertRedirects(
            response,
            reverse(
                "schemes:scheme_detail",
                kwargs={
                    "pk": created_scheme.pk,
                },
            ),
        )

    def test_scheme_update(
        self,
    ) -> None:
        """Існуючу схему можна відредагувати."""

        response = self.client.post(
            reverse(
                "schemes:scheme_update",
                kwargs={
                    "pk": self.scheme.pk,
                },
            ),
            data=self.get_form_data(
                title="Оновлений браслет",
                description=(
                    "Оновлений опис схеми"
                ),
            ),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.scheme.refresh_from_db()

        self.assertEqual(
            self.scheme.title,
            "Оновлений браслет",
        )

        self.assertEqual(
            self.scheme.description,
            "Оновлений опис схеми",
        )

    def test_toggle_favorite_requires_post(
        self,
    ) -> None:
        """Обране не можна змінити через GET-запит."""

        response = self.client.get(
            reverse(
                "schemes:scheme_toggle_favorite",
                kwargs={
                    "pk": self.scheme.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            405,
        )

    def test_toggle_favorite_in_session(
        self,
    ) -> None:
        """
        Схему можна додати до обраного
        та прибрати із сесії браузера.
        """

        url = reverse(
            "schemes:scheme_toggle_favorite",
            kwargs={
                "pk": self.scheme.pk,
            },
        )

        first_response = self.client.post(
            url
        )

        self.assertRedirects(
            first_response,
            reverse(
                "schemes:scheme_detail",
                kwargs={
                    "pk": self.scheme.pk,
                },
            ),
        )

        favorite_ids = self.client.session.get(
            FAVORITE_SCHEMES_SESSION_KEY,
            [],
        )

        self.assertIn(
            self.scheme.pk,
            favorite_ids,
        )

        self.client.post(
            url
        )

        favorite_ids = self.client.session.get(
            FAVORITE_SCHEMES_SESSION_KEY,
            [],
        )

        self.assertNotIn(
            self.scheme.pk,
            favorite_ids,
        )

    def test_favorites_are_separate_for_browsers(
        self,
    ) -> None:
        """
        Різні браузерні сесії мають
        різні списки обраних схем.
        """

        second_client = Client()

        url = reverse(
            "schemes:scheme_toggle_favorite",
            kwargs={
                "pk": self.scheme.pk,
            },
        )

        self.client.post(
            url
        )

        first_client_favorites = (
            self.client.session.get(
                FAVORITE_SCHEMES_SESSION_KEY,
                [],
            )
        )

        second_client_favorites = (
            second_client.session.get(
                FAVORITE_SCHEMES_SESSION_KEY,
                [],
            )
        )

        self.assertIn(
            self.scheme.pk,
            first_client_favorites,
        )

        self.assertNotIn(
            self.scheme.pk,
            second_client_favorites,
        )

    def test_delete_confirmation_page(
        self,
    ) -> None:
        """
        Перед видаленням відкривається
        сторінка підтвердження.
        """

        response = self.client.get(
            reverse(
                "schemes:scheme_delete",
                kwargs={
                    "pk": self.scheme.pk,
                },
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "schemes/scheme_confirm_delete.html",
        )

        self.assertContains(
            response,
            "Браслет із ромашками",
        )

    def test_scheme_delete(
        self,
    ) -> None:
        """Схему можна видалити після POST-запиту."""

        scheme_pk = self.scheme.pk

        favorite_url = reverse(
            "schemes:scheme_toggle_favorite",
            kwargs={
                "pk": scheme_pk,
            },
        )

        self.client.post(
            favorite_url
        )

        response = self.client.post(
            reverse(
                "schemes:scheme_delete",
                kwargs={
                    "pk": scheme_pk,
                },
            )
        )

        self.assertFalse(
            Scheme.objects.filter(
                pk=scheme_pk
            ).exists()
        )

        favorite_ids = self.client.session.get(
            FAVORITE_SCHEMES_SESSION_KEY,
            [],
        )

        self.assertNotIn(
            scheme_pk,
            favorite_ids,
        )

        self.assertRedirects(
            response,
            reverse(
                "schemes:scheme_list"
            ),
        )