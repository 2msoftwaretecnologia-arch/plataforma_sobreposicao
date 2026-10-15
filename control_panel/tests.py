from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from .access_service import denied_layers, filter_result, filter_batch_item, require_layer


class LayerAccessTests(SimpleTestCase):
    def policy(self, model, groups=()):
        policy = SimpleNamespace(modelo=model, grupos=Mock())
        policy.grupos.all.return_value = [SimpleNamespace(pk=g) for g in groups]
        return policy

    def user(self, groups=(), staff=False, active=True):
        user = SimpleNamespace(is_authenticated=True, is_active=active, is_staff=staff, is_superuser=False, groups=Mock())
        user.groups.values_list.return_value = groups
        return user

    @patch('control_panel.access_service.LayerAccessPolicy.objects')
    def test_groups_admin_anonymous_and_inactive(self, objects):
        objects.filter.return_value.prefetch_related.return_value = [self.policy('Ipuca', [1]), self.policy('Sigef')]
        self.assertEqual(denied_layers(self.user([1])), {'Sigef'})
        self.assertEqual(denied_layers(self.user()), {'Ipuca', 'Sigef'})
        self.assertEqual(denied_layers(AnonymousUser()), {'Ipuca', 'Sigef'})
        self.assertEqual(denied_layers(self.user([1], active=False)), {'Ipuca', 'Sigef'})
        self.assertEqual(denied_layers(self.user(staff=True)), set())

    @patch('control_panel.access_service.denied_layers', return_value={'Ipuca', 'PhytoecologyArea'})
    def test_saved_result_removes_data_and_rebuilds_totals(self, denied):
        data = {'resultado': {'resultados_por_base': [
            {'nome_base': 'Base de Dados IPUCA', 'areas_encontradas': [{'secret': 1}]},
            {'nome_base': 'Base de Dados Sigef', 'areas_encontradas': [{'area': 2}]}],
            'resumo_bases': {'Base de Dados IPUCA': 123, 'Base de Dados Sigef': 2},
            'poligonos_imoveis': [{'fonte': 'Base de Dados IPUCA'}], 'area_preservada_total': 50}}
        result = filter_result(data)['resultado']
        self.assertEqual(result['areas_encontradas'], [{'area': 2}])
        self.assertEqual(result['total_areas_com_sobreposicao'], 1)
        self.assertEqual(result['poligonos_imoveis'], [])
        self.assertEqual(result['resumo_bases'], {'Base de Dados Sigef': 2})
        self.assertEqual(result['area_preservada_total'], 0)
        self.assertEqual(len(data['resultado']['resultados_por_base']), 2)

    @patch('control_panel.access_service.denied_layers', return_value={'Sigef'})
    def test_source_revocation_and_direct_access(self, denied):
        with self.assertRaises(PermissionDenied):
            require_layer('Sigef')
        with self.assertRaises(PermissionDenied):
            filter_result({'source_model': 'Sigef', 'car_input': 'code'})

    @patch('control_panel.access_service.denied_layers', return_value={'Ipuca'})
    def test_batch_revocation_recalculates_counts(self, denied):
        item = SimpleNamespace(summary={'bases': [
            {'nome': 'Base de Dados IPUCA', 'count': 5, 'severity': 'critical'},
            {'nome': 'Base de Dados Sigef', 'count': 2, 'severity': 'warning'}]})
        filter_batch_item(item)
        self.assertEqual(item.overlap_count, 2)
        self.assertEqual(item.critical_count, 0)
        self.assertEqual(item.warning_count, 1)

    @patch('control_panel.access_service.denied_layers', return_value={'Secret'})
    def test_pipeline_never_queries_denied_layers(self, denied):
        from analysis.services.analyze_coordinates.search_all import SearchAll
        secret, public = type('Secret', (), {}), type('Public', (), {})
        search = SearchAll.__new__(SearchAll)
        search.user = None
        search.formatters = SimpleNamespace(formatters={secret: None, public: None})
        self.assertEqual(search._get_layers(), [public])

    def test_employee_has_no_panel_access(self):
        from .urls import _staff_only
        view = Mock()
        request = RequestFactory().post('/painel/usuarios/')
        request.user = self.user([1])
        self.assertEqual(_staff_only(view)(request).status_code, 302)
        view.assert_not_called()

    def test_templates_compile(self):
        from django.template.loader import get_template
        for name in ['usuarios', 'bases_dados']:
            get_template('control_panel/' + name + '.html')


    @patch('analysis.views.get_sicar_record')
    @patch('analysis.views.SearchForCar')
    def test_car_upload_passes_user_to_search(self, search, records):
        from analysis.views import UploadZipCarView
        user = self.user([1])
        search.return_value.execute.return_value = {'ok': True}
        records.return_value.exists.return_value = False
        result, _, _ = UploadZipCarView()._get_car_data('CAR', user)
        search.return_value.execute.assert_called_once_with('CAR', user=user)
        self.assertEqual(result, {'ok': True})

    @patch('analysis.views.render_tile')
    @patch('control_panel.access_service.denied_layers', return_value={'Ipuca'})
    def test_restricted_tile_is_blocked_before_cache(self, denied, render):
        from analysis.views import BaseTileView
        request = RequestFactory().get('/tile/')
        request.user = self.user()
        with self.assertRaises(PermissionDenied):
            BaseTileView().get(request, 'Ipuca', 5, 0, 0)
        render.assert_not_called()
