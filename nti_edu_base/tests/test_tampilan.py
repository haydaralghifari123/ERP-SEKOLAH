# -*- coding: utf-8 -*-
from odoo.tests import Form, tagged

from .common import NtiEduCommon

ACTIONS = [
    'action_siswa', 'action_rombel', 'action_wali', 'action_tahun_ajaran', 'action_hari_libur',
    'action_unit', 'action_jenjang', 'action_jurusan', 'action_mapel', 'action_ruang',
]


@tagged('post_install', '-at_install')
class TestTampilan(NtiEduCommon):

    def test_semua_action_terbuka(self):
        for xmlid in ACTIONS:
            action = self.env.ref('nti_edu_base.' + xmlid)
            model = self.env[action.res_model].with_user(self.user_operator_smp)
            for mode in action.view_mode.split(','):
                view = action.view_ids.filtered(lambda v: v.view_mode == mode).view_id
                if mode == 'form' and not view:
                    view = action.view_id
                with self.subTest(action=xmlid, mode=mode):
                    hasil = model.get_views([(view.id or False, mode)])
                    self.assertIn(mode, hasil['views'])

    def test_menu_konfigurasi_khusus_admin(self):
        menu = self.env.ref('nti_edu_base.menu_konfigurasi')
        admin = self._buat_user('tes_admin_smp', 'nti_edu_base.group_base_admin', self.unit_smp)
        Menu = self.env['ir.ui.menu']
        self.assertNotIn(menu.id, Menu.with_user(self.user_operator_smp)._visible_menu_ids())
        self.assertIn(menu.id, Menu.with_user(admin)._visible_menu_ids())
        root = self.env.ref('nti_edu_base.menu_data_sekolah')
        self.assertIn(root.id, Menu.with_user(self.user_guru_smp)._visible_menu_ids())

    def test_form_siswa_guru(self):
        siswa = self._buat_siswa('Siswa Tampil', self.unit_smp, '001')
        form = Form(siswa.with_user(self.user_guru_smp), view='nti_edu_base.view_siswa_form')
        self.assertEqual(form.name, 'Siswa Tampil')

    def test_form_siswa_operator(self):
        siswa = self._buat_siswa('Siswa Tampil 2', self.unit_smp, '002')
        form = Form(siswa.with_user(self.user_operator_smp), view='nti_edu_base.view_siswa_form')
        self.assertEqual(form.nti_edu_nis, '002')
