import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from web.main import app, parse_excel, session


def excel(formula=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['SKU', 'Stock Disponible', 'Familia'])
    sheet.append([12, '=1+1' if formula else 4, 'Colchones'])
    sheet['A2'].number_format = '00000'
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


class UploadTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[session] = lambda: 'test-token'
        self.client = TestClient(app)
        self.remote = AsyncMock(return_value=[{'rol': 'administrador'}])
        self.patcher = patch('web.main.request', self.remote)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        app.dependency_overrides.clear()
        self.client.close()

    def send(self, endpoint, content, digest=None):
        return self.client.post(endpoint, files={'file': ('stock.xlsx', content)},
                                headers={'X-Preview-SHA256': digest} if digest else {})

    def test_preview_does_not_write_and_preserves_sku(self):
        result = self.send('/api/preview', excel())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['filas'][0][0], '00012')
        self.assertEqual(result.json()['cantidad'], 1)
        self.assertTrue(all(call.args[0] == 'GET' for call in self.remote.call_args_list))

    def test_reviewed_upload_writes_once(self):
        content = excel()
        digest = self.send('/api/preview', content).json()['sha256']
        result = self.send('/api/upload', content, digest)
        self.assertEqual(result.status_code, 200)
        writes = [call for call in self.remote.call_args_list if call.args[0] == 'POST']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[1], '/rest/v1/rpc/guardar_excel')

    def test_successful_publication_notifies_connected_devices(self):
        content = excel()
        digest = self.send('/api/preview', content).json()['sha256']
        with patch('web.main.notify_stock_updated') as notify:
            self.assertEqual(self.send('/api/upload', content, digest).status_code, 200)
            notify.assert_called_once()

    def test_failed_publication_does_not_notify_devices(self):
        from fastapi import HTTPException
        content = excel()
        digest = self.send('/api/preview', content).json()['sha256']
        self.remote.side_effect = [[{'rol': 'administrador'}], HTTPException(502, 'Error al guardar')]
        with patch('web.main.notify_stock_updated') as notify:
            self.assertEqual(self.send('/api/upload', content, digest).status_code, 502)
            notify.assert_not_called()

    def test_admin_can_delete_with_confirmation(self):
        with patch('web.main.notify_stock_updated') as notify:
            result = self.client.request('DELETE', '/api/excel-actual', json={'confirmar': True})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.remote.call_args.args, ('DELETE', '/rest/v1/excel_actual?id=eq.1', 'test-token'))
            notify.assert_called_once()

    def test_delete_without_confirmation_does_not_write(self):
        with patch('web.main.notify_stock_updated') as notify:
            result = self.client.request('DELETE', '/api/excel-actual', json={'confirmar': False})
            self.assertEqual(result.status_code, 400)
            self.assertEqual(self.remote.call_count, 1)
            notify.assert_not_called()

    def test_viewer_cannot_delete(self):
        self.remote.return_value = [{'rol': 'visualizador'}]
        result = self.client.request('DELETE', '/api/excel-actual', json={'confirmar': True})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.remote.call_count, 1)

    def test_failed_delete_does_not_notify(self):
        from fastapi import HTTPException
        self.remote.side_effect = [[{'rol': 'administrador'}], HTTPException(502, 'Error')]
        with patch('web.main.notify_stock_updated') as notify:
            result = self.client.request('DELETE', '/api/excel-actual', json={'confirmar': True})
            self.assertEqual(result.status_code, 502)
            notify.assert_not_called()

    def test_missing_or_mismatched_preview_never_writes(self):
        for digest in (None, 'not-the-reviewed-file'):
            self.assertEqual(self.send('/api/upload', excel(), digest).status_code, 400)
        self.assertTrue(all(call.args[0] == 'GET' for call in self.remote.call_args_list))

    def test_invalid_workbook_never_writes(self):
        self.assertEqual(self.send('/api/preview', b'not excel').status_code, 400)
        self.assertEqual(self.send('/api/upload', b'not excel', 'invalid').status_code, 400)
        self.assertTrue(all(call.args[0] == 'GET' for call in self.remote.call_args_list))

    def test_viewer_cannot_preview_or_publish(self):
        self.remote.return_value = [{'rol': 'visualizador'}]
        for endpoint in ('/api/preview', '/api/upload'):
            self.assertEqual(self.send(endpoint, excel()).status_code, 403)
        self.assertTrue(all(call.args[0] == 'GET' for call in self.remote.call_args_list))

    def test_formula_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'fórmulas'):
            parse_excel(excel(formula=True))

    def test_viewer_cannot_access_administrative_data(self):
        self.remote.return_value = [{'rol': 'visualizador'}]
        result = self.client.get('/api/administrativo')
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.remote.call_count, 1)

    def test_profile_reports_server_assigned_role(self):
        for role in ('administrador', 'visualizador'):
            self.remote.return_value = [{'rol': role}]
            result = self.client.get('/api/me')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), {'rol': role})

    def test_login_returns_renewable_session(self):
        session_data = {'access_token': 'access-test', 'refresh_token': 'refresh-test', 'expires_in': 3600}
        self.remote.return_value = session_data
        response = self.client.post('/api/login', json={'email': 'admin@example.com', 'password': 'test-only'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), session_data)

    def test_refresh_rotates_session(self):
        session_data = {'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_in': 3600}
        self.remote.return_value = session_data
        response = self.client.post('/api/refresh', json={'refresh_token': 'old-refresh'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), session_data)
        self.assertEqual(self.remote.call_args.args, ('POST', '/auth/v1/token?grant_type=refresh_token'))
        self.assertEqual(self.remote.call_args.kwargs['json'], {'refresh_token': 'old-refresh'})

    def test_missing_profile_is_denied(self):
        self.remote.return_value = []
        self.assertEqual(self.client.get('/api/me').status_code, 403)

    def test_viewer_cannot_read_history(self):
        self.remote.return_value = [{'rol': 'visualizador'}]
        self.assertEqual(self.client.get('/api/historial').status_code, 403)
        self.assertEqual(self.remote.call_count, 1)

    def test_guest_cannot_read_history(self):
        app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/api/historial').status_code, 401)
        self.remote.assert_not_called()

    def test_history_is_paginated(self):
        rows = [{'id': str(index), 'email': 'admin@example.com'} for index in range(26)]
        self.remote.side_effect = [[{'rol': 'administrador'}], rows]
        response = self.client.get('/api/historial?offset=25')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['registros']), 25)
        self.assertTrue(response.json()['hay_mas'])
        self.assertIn('offset=25', self.remote.call_args.args[1])

    def test_history_rejects_negative_offset(self):
        self.assertEqual(self.client.get('/api/historial?offset=-1').status_code, 422)

    def test_person_history_is_filtered_and_paginated(self):
        self.remote.side_effect = [[{'rol': 'administrador'}], [{'entrada': '2026-11-05'}] * 26]
        result = self.client.get('/api/actividad/historial', params={
            'nombre': 'Ana Pérez', 'tipo': 'vendedor', 'offset': 25,
        })
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()['accesos']), 25)
        self.assertTrue(result.json()['hay_mas'])
        params = self.remote.call_args.kwargs['params']
        self.assertEqual(params['nombre'], 'eq.Ana Pérez')
        self.assertEqual(params['tipo'], 'eq.vendedor')
        self.assertEqual(params['offset'], 25)

    def test_viewer_cannot_read_person_history(self):
        self.remote.return_value = [{'rol': 'visualizador'}]
        result = self.client.get('/api/actividad/historial', params={'nombre': 'Ana', 'tipo': 'vendedor'})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.remote.call_count, 1)

    def test_activity_is_private_for_guests_and_viewers(self):
        self.remote.return_value = [{'rol': 'visualizador'}]
        self.assertEqual(self.client.get('/api/actividad').status_code, 403)
        app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/api/actividad').status_code, 401)

    def test_admin_activity_is_paginated(self):
        records = [{'nombre': 'Vendedor'} for _ in range(26)]
        self.remote.side_effect = [[{'rol': 'administrador'}], {'personas': [], 'accesos': records}]
        result = self.client.get('/api/actividad?offset=25')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()['accesos']), 25)
        self.assertTrue(result.json()['hay_mas'])

    def test_seller_activity_does_not_accept_client_role(self):
        from uuid import uuid4
        app.dependency_overrides.clear()
        self.remote.return_value = None
        result = self.client.post('/api/actividad', json={
            'visita': str(uuid4()), 'dispositivo': str(uuid4()),
            'nombre': 'Ana', 'apellido': 'Perez', 'rol': 'administrador',
        })
        self.assertEqual(result.status_code, 200)
        call = self.remote.call_args
        self.assertIsNone(call.args[2])
        self.assertNotIn('rol', call.kwargs['json'])

    def test_seller_activity_requires_name(self):
        from uuid import uuid4
        app.dependency_overrides.clear()
        result = self.client.post('/api/actividad', json={
            'visita': str(uuid4()), 'dispositivo': str(uuid4()), 'nombre': '', 'apellido': '',
        })
        self.assertEqual(result.status_code, 400)
        self.remote.assert_not_called()

    def test_seller_stock_uses_anonymous_read_only_query(self):
        snapshot = {'columnas': ['SKU'], 'filas': [['00012']]}
        self.remote.return_value = [snapshot]
        result = self.client.get('/api/stock-vendedores')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), snapshot)
        call = self.remote.call_args
        self.assertEqual(call.args[0], 'GET')
        self.assertEqual(len(call.args), 2)

    def test_guest_name_does_not_grant_admin_permissions(self):
        app.dependency_overrides.clear()
        for endpoint in ('/api/me', '/api/administrativo'):
            result = self.client.get(endpoint, headers={'X-Nombre': 'Administrador'})
            self.assertEqual(result.status_code, 401)
        for endpoint in ('/api/upload', '/api/preview'):
            self.assertEqual(self.send(endpoint, excel()).status_code, 401)
        self.remote.assert_not_called()

    def test_admin_can_access_administrative_data(self):
        snapshot = {'nombre': 'stock.xlsx', 'columnas': ['SKU'], 'filas': [['001']]}
        self.remote.side_effect = [[{'rol': 'administrador'}], [snapshot]]
        result = self.client.get('/api/administrativo')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), snapshot)

    def test_preview_limits_sample_to_ten_rows(self):
        workbook = Workbook()
        workbook.active.append(['SKU'])
        for index in range(25):
            workbook.active.append([str(index)])
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()
        result = self.send('/api/preview', buffer.getvalue()).json()
        self.assertEqual(result['cantidad'], 25)
        self.assertEqual(len(result['filas']), 10)


if __name__ == '__main__':
    unittest.main()
