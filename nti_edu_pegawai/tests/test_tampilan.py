# -*- coding: utf-8 -*-
from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import NtiPegawaiCommon


@tagged('post_install', '-at_install')
class TestTampilan(NtiPegawaiCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.budi_smp = cls._buat_pegawai('Budi', cls.unit_smp)
        cls.budi_sma = cls._buat_pegawai(
            'Budi', cls.unit_sma, work_contact_id=cls.budi_smp.work_contact_id.id)
        cls.sari = cls._buat_pegawai('Sari', cls.unit_smp)

    def _sebagai(self, rec, user):
        return rec.with_user(user).with_context(allowed_company_ids=user.company_ids.ids)

    def _menu_terlihat(self, user):
        menu = self.env.ref('nti_edu_pegawai.menu_pegawai')
        return menu.id in self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()

    def test_menu_terlihat_sesuai_grup(self):
        self.assertTrue(self._menu_terlihat(self.tu_smp))
        self.assertTrue(self._menu_terlihat(self.hrd))
        self.assertFalse(self._menu_terlihat(self.guru_smp))
        menu = self.env.ref('nti_edu_pegawai.menu_pegawai')
        self.assertEqual(menu.parent_id, self.env.ref('nti_edu_base.menu_data_sekolah'))

    def _views(self, user):
        action = self.env.ref('nti_edu_pegawai.action_pegawai')
        self.assertEqual(action.res_model, 'hr.employee')
        self.assertEqual(action.view_mode, 'kanban,list,form')
        pasangan = [(action.view_ids.filtered(lambda v: v.view_mode == m).view_id.id, m)
                    for m in ('kanban', 'list', 'form')]
        return self._sebagai(self.env['hr.employee'], user).get_views(pasangan)['views']

    def test_view_action_terbuka_untuk_tu(self):
        views = self._views(self.tu_smp)
        for mode in ('kanban', 'list', 'form'):
            self.assertIn(mode, views)

    def test_form_punya_tab_kepegawaian(self):
        form = etree.fromstring(self._views(self.tu_smp)['form']['arch'])
        halaman = form.xpath('//page[@name="page_kepegawaian"]')
        self.assertEqual(len(halaman), 1)
        for nama in ('nti_edu_nuptk', 'nti_edu_nik', 'nti_edu_jenis_ptk', 'nti_edu_tmt', 'nti_edu_sertifikasi_ids'):
            self.assertTrue(halaman[0].xpath('.//field[@name=$n]', n=nama), nama)

    def test_kanban_tanpa_kanban_image(self):
        arch = self._views(self.tu_smp)['kanban']['arch']
        kanban = etree.fromstring(arch)
        self.assertTrue(kanban.xpath('//t[@t-name="card"]'))
        for atribut in kanban.xpath('//@*'):
            self.assertNotRegex(atribut, r'\b(kanban_image|user_context)\b')
        self.assertEqual(len(kanban.xpath('//field[@name="avatar_128" and @widget="image"]')), 1)

    def test_sertifikasi_lewat_form_pegawai_dijaga(self):
        Sert = self.env['nti_edu.pegawai.sertifikasi']
        with self.assertRaises(AccessError):
            self._sebagai(self.budi_sma, self.tu_sma).write({
                'nti_edu_sertifikasi_ids': [(0, 0, {'nomor': 'BLOK', 'jenis': 'pendidik'})]})
        self.assertFalse(Sert.search([('nomor', '=', 'BLOK')]))

    def test_sertifikasi_lewat_form_pegawai_boleh(self):
        self._sebagai(self.sari, self.tu_smp).write({
            'nti_edu_sertifikasi_ids': [(0, 0, {'nomor': 'OK-1', 'jenis': 'pendidik', 'tahun': 2020})]})
        sert = self.env['nti_edu.pegawai.sertifikasi'].search([('nomor', '=', 'OK-1')])
        self.assertEqual(len(sert), 1)
        self.assertEqual(sert.partner_id, self.sari.work_contact_id)
        self.assertEqual(self.sari.work_contact_id.nti_edu_sertifikasi_ids, sert)
