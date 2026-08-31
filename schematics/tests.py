from django.test import TestCase


from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Brand, PhoneModel, SchematicCategory, Schematic


class SchematicsAPITests(APITestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name='Samsung', slug='samsung')
        self.phone_model = PhoneModel.objects.create(
            brand=self.brand,
            name='Galaxy S23 Ultra',
            slug='galaxy-s23-ultra',
            technical_code='SM-S918B'
        )
        self.category = SchematicCategory.objects.create(
            title='Schematic Diagram',
            slug='schematic-diagram'
        )
        self.schematic = Schematic.objects.create(
            phone_model=self.phone_model,
            category=self.category,
            title='Main Board Schematic',
            is_free=True,
            price=0
        )
        self.list_url = reverse('schematics:schematic-list')
        self.detail_url = reverse('schematics:schematic-detail', kwargs={'pk': self.schematic.pk})

    def test_get_schematics_list(self):
        """تست دریافت لیست شماتیک‌ها"""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Main Board Schematic')
        self.assertEqual(response.data[0]['brand_name'], 'Samsung')

    def test_search_schematic_by_technical_code(self):
        """تست سرچ شماتیک بر اساس کد فنی برد (SM-S918B)"""
        response = self.client.get(self.list_url, {'search': 'SM-S918B'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_schematic_detail_and_view_count_increment(self):
        """تست دریافت جزئیات و افزایش خودکار تعداد بازدید"""
        initial_views = self.schematic.view_count
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.schematic.refresh_from_db()
        self.assertEqual(self.schematic.view_count, initial_views + 1)