# -*- coding: utf-8 -*-
from datetime import date, timedelta

from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged

from .common import NtiEduCommon


@tagged('post_install', '-at_install')
class TestTambahRombel(NtiEduCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        hari_ini = date.today()
        Tahun = cls.env['nti_edu.tahun.ajaran']
        cls.ta_aktif = Tahun.create({
            'name': 'TA Berjalan', 'tanggal_mulai': hari_ini - timedelta(days=100),
            'tanggal_selesai': hari_ini + timedelta(days=200), 'is_aktif': True})
        cls.ta_depan = Tahun.create({
            'name': 'TA Depan', 'tanggal_mulai': hari_ini + timedelta(days=300),
            'tanggal_selesai': hari_ini + timedelta(days=600)})
        ref = cls.env.ref
        cls.rombel_smp = cls._rombel('VII A', cls.ta_aktif, ref('nti_edu_base.tingkat_smp_7'), cls.unit_smp)
        cls.rombel_smp_b = cls._rombel('VII B', cls.ta_aktif, ref('nti_edu_base.tingkat_smp_7'), cls.unit_smp)
        cls.rombel_depan = cls._rombel('VIII A', cls.ta_depan, ref('nti_edu_base.tingkat_smp_8'), cls.unit_smp)
        cls.rombel_sma = cls._rombel('X IPA 1', cls.ta_aktif, ref('nti_edu_base.tingkat_sma_10'), cls.unit_sma)
        cls.a = cls._buat_siswa('Siswa A', cls.unit_smp, 'T001')
        cls.b = cls._buat_siswa('Siswa B', cls.unit_smp, 'T002')
        cls.c = cls._buat_siswa('Siswa C', cls.unit_sma, 'T003')

    @classmethod
    def _rombel(cls, nama, tahun, tingkat, unit):
        return cls.env['nti_edu.rombel'].create({
            'name': nama, 'tahun_ajaran_id': tahun.id, 'tingkat_id': tingkat.id, 'company_id': unit.id})

    def _wizard(self, siswa, rombel, user=None):
        """user=False: superuser (agar siswa unit lain terbaca)."""
        Wizard = self.env['nti_edu.tambah.rombel.wizard']
        if user is not False:
            Wizard = Wizard.with_user(user or self.user_operator_smp)
        return Wizard.create({'rombel_id': rombel.id, 'siswa_ids': [(6, 0, siswa.ids)]})

    def _anggota(self, siswa):
        return self.env['nti_edu.rombel.anggota'].search([('siswa_id', 'in', siswa.ids)])

    def test_tambah_dua_siswa(self):
        Wizard = self.env['nti_edu.tambah.rombel.wizard'].with_user(self.user_operator_smp).with_context(
            active_model='res.partner', active_ids=[self.a.id, self.b.id])
        wizard = Wizard.create({'rombel_id': self.rombel_smp.id})
        self.assertEqual(wizard.siswa_ids, self.a | self.b)
        self.assertEqual(wizard.action_tambah(), {'type': 'ir.actions.act_window_close'})
        for siswa in (self.a, self.b):
            anggota = self._anggota(siswa)
            self.assertEqual(anggota.rombel_id, self.rombel_smp)
            self.assertEqual(anggota.tanggal_masuk, date.today())

    def test_tanggal_masuk_tahun_depan(self):
        Wizard = self.env['nti_edu.tambah.rombel.wizard'].with_user(self.user_operator_smp)
        form = Form(Wizard, view='nti_edu_base.view_tambah_rombel_wizard_form')
        form.rombel_id = self.rombel_depan
        self.assertEqual(form.tanggal_masuk, self.ta_depan.tanggal_mulai)
        form.rombel_id = self.rombel_smp
        self.assertEqual(form.tanggal_masuk, date.today())

    def test_siswa_unit_lain_ditolak_tanpa_sebagian(self):
        wizard = self._wizard(self.a | self.c, self.rombel_smp, user=False)
        with self.assertRaises(UserError) as ctx:
            wizard.action_tambah()
        self.assertIn(self.c.name, str(ctx.exception))
        self.assertFalse(self._anggota(self.a))

    def test_siswa_sudah_di_rombel_tahun_sama_ditolak(self):
        self.env['nti_edu.rombel.anggota'].create({'rombel_id': self.rombel_smp_b.id, 'siswa_id': self.a.id})
        wizard = self._wizard(self.a | self.b, self.rombel_smp)
        with self.assertRaises(UserError) as ctx:
            wizard.action_tambah()
        self.assertIn(self.a.name, str(ctx.exception))
        self.assertFalse(self._anggota(self.b))

    def test_siswa_tidak_aktif_ditolak(self):
        self.b.nti_edu_status = 'lulus'
        wizard = self._wizard(self.a | self.b, self.rombel_smp)
        with self.assertRaises(UserError) as ctx:
            wizard.action_tambah()
        self.assertIn(self.b.name, str(ctx.exception))
        self.assertFalse(self._anggota(self.a))

    def test_bukan_siswa_ditolak(self):
        biasa = self.env['res.partner'].create({'name': 'Kontak Biasa', 'company_id': self.unit_smp.id})
        wizard = self._wizard(biasa, self.rombel_smp, user=False)
        with self.assertRaises(UserError):
            wizard.action_tambah()

    def test_id_tidak_terbaca_ditolak(self):
        Wizard = self.env['nti_edu.tambah.rombel.wizard'].with_user(self.user_operator_smp).with_context(
            active_model='res.partner', active_ids=[self.a.id, self.c.id])
        wizard = Wizard.create({'rombel_id': self.rombel_smp.id})
        with self.assertRaises(UserError) as ctx:
            wizard.action_tambah()
        self.assertIn('tidak dapat diakses', str(ctx.exception))
        self.assertNotIn(self.c.name, str(ctx.exception))
        self.assertFalse(self._anggota(self.a))

    def test_siswa_yang_dihapus_dari_pilihan_tidak_ditambahkan(self):
        Wizard = self.env['nti_edu.tambah.rombel.wizard'].with_user(self.user_operator_smp).with_context(
            active_model='res.partner', active_ids=[self.a.id, self.b.id])
        wizard = Wizard.create({'rombel_id': self.rombel_smp.id})
        wizard.siswa_ids = [(3, self.b.id)]
        wizard.action_tambah()
        self.assertTrue(self._anggota(self.a))
        self.assertFalse(self._anggota(self.b))

    def test_id_tak_terbaca_hanya_di_pilihan_wizard_ditolak(self):
        wizard = self._wizard(self.a, self.rombel_smp)
        wizard.sudo().siswa_ids = [(4, self.c.id)]
        with self.assertRaises(UserError) as ctx:
            wizard.action_tambah()
        self.assertIn('tidak dapat diakses', str(ctx.exception))
        self.assertNotIn(self.c.name, str(ctx.exception))
        self.assertFalse(self._anggota(self.a | self.c))

    def test_guru_tidak_bisa(self):
        with self.assertRaises(AccessError):
            self.env['nti_edu.tambah.rombel.wizard'].with_user(self.user_guru_smp).create({
                'rombel_id': self.rombel_smp.id})

    def test_tombol_di_list_siswa(self):
        aksi = self.env.ref('nti_edu_base.action_tambah_rombel_wizard')
        arch = self.env['res.partner'].with_user(self.user_operator_smp).get_views(
            [(self.env.ref('nti_edu_base.view_siswa_list').id, 'list')])['views']['list']['arch']
        tombol = etree.fromstring(arch).xpath('//header/button[@name=$n and @type="action"]', n=str(aksi.id))
        self.assertEqual(len(tombol), 1)
        # get_views membuang atribut groups bagi user yang berhak; periksa arch sumbernya.
        sumber = etree.fromstring(self.env.ref('nti_edu_base.view_siswa_list').arch)
        self.assertEqual(
            sumber.xpath('//header/button[@type="action"]')[0].get('groups'), 'nti_edu_base.group_base_operator')
        self.assertEqual(aksi.target, 'new')
        arch_guru = self.env['res.partner'].with_user(self.user_guru_smp).get_views(
            [(self.env.ref('nti_edu_base.view_siswa_list').id, 'list')])['views']['list']['arch']
        self.assertFalse(etree.fromstring(arch_guru).xpath('//button[@name=$n]', n=str(aksi.id)))
