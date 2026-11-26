# -*- coding: utf-8 -*-
from datetime import date

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import NtiTagihanCommon


@tagged('post_install', '-at_install')
class TestSkemaPotongan(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tingkat_7 = cls.env.ref('nti_edu_base.tingkat_smp_7')
        cls.tingkat_8 = cls.env.ref('nti_edu_base.tingkat_smp_8')
        cls.tanpa_jurusan = cls.env['nti_edu.jurusan']
        cls.jurusan = cls.env['nti_edu.jurusan'].create({'name': 'Jurusan J', 'company_id': cls.unit_smp.id})
        cls.spp = cls._buat_komponen('SPP Skema', 'periode_bulanan')
        cls.pangkal = cls._buat_komponen('Pangkal Skema', 'periode_sekali')

    def _skema(self, unit=None, ta=None, state='draft', baris=()):
        return self.env['nti_edu.tagihan.skema'].create({
            'company_id': (unit or self.unit_smp).id,
            'tahun_ajaran_id': (ta or self.ta).id,
            'state': state,
            'baris_ids': [(0, 0, {
                'komponen_id': k.id, 'tingkat_id': t.id if t else False,
                'jurusan_id': j.id if j else False, 'nominal': n}) for k, t, j, n in baris],
        })

    def _jenis(self, nama, tipe, nilai, gabung=True, persetujuan=False, komponen=None):
        komponen = self.spp if komponen is None else komponen
        return self.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': nama, 'tipe': tipe, 'nilai_bawaan': nilai, 'dapat_digabung': gabung,
            'perlu_persetujuan': persetujuan, 'komponen_ids': [(6, 0, komponen.ids)]})

    def _potongan(self, siswa, jenis, nilai=None, mulai=date(2026, 7, 1), selesai=False, aktif=True):
        pot = self.env['nti_edu.tagihan.potongan'].create({
            'siswa_id': siswa.id, 'jenis_id': jenis.id,
            'nilai': jenis.nilai_bawaan if nilai is None else nilai,
            'tanggal_mulai': mulai, 'tanggal_selesai': selesai})
        if aktif:
            pot.action_ajukan()
        return pot

    def test_baris_paling_spesifik(self):
        skema = self._skema(baris=[
            (self.spp, False, False, 100000),
            (self.spp, self.tingkat_7, False, 150000),
            (self.spp, self.tingkat_7, self.jurusan, 175000)])
        self.assertEqual(skema._baris_untuk(self.spp, self.tingkat_7, self.jurusan).nominal, 175000)
        self.assertEqual(skema._baris_untuk(self.spp, self.tingkat_7, self.tanpa_jurusan).nominal, 150000)
        self.assertEqual(skema._baris_untuk(self.spp, self.tingkat_8, self.tanpa_jurusan).nominal, 100000)
        self.assertEqual(skema._baris_untuk(self.spp, self.tingkat_8, self.jurusan).nominal, 100000)
        self.assertFalse(skema._baris_untuk(self.pangkal, self.tingkat_7, self.jurusan))

    def test_baris_jurusan_saja(self):
        skema = self._skema(baris=[
            (self.spp, False, False, 100000),
            (self.spp, False, self.jurusan, 120000)])
        self.assertEqual(skema._baris_untuk(self.spp, self.tingkat_8, self.jurusan).nominal, 120000)

    def test_baris_ganda_ditolak(self):
        skema = self._skema(baris=[(self.spp, self.tingkat_7, False, 100000)])
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), \
                self.cr.savepoint():
            self.env['nti_edu.tagihan.skema.baris'].create({
                'skema_id': skema.id, 'komponen_id': self.spp.id, 'tingkat_id': self.tingkat_7.id,
                'nominal': 200000})

    def test_komponen_denda_ditolak(self):
        denda = self.env['nti_edu.tagihan.komponen'].create({'name': 'Denda Skema', 'jenis': 'denda'})
        with self.assertRaises(ValidationError):
            self._skema(baris=[(denda, False, False, 10000)])

    def test_satu_skema_aktif(self):
        self._skema(state='aktif')
        with self.assertRaises(ValidationError):
            self._skema(state='aktif')
        sma = self._skema(unit=self.unit_sma, state='aktif')
        self.assertEqual(sma.state, 'aktif')
        draft = self._skema()
        with self.assertRaises(ValidationError):
            draft.action_aktifkan()

    def test_aktif_untuk_dan_arsip(self):
        skema = self._skema()
        skema.action_aktifkan()
        Skema = self.env['nti_edu.tagihan.skema']
        self.assertEqual(Skema._aktif_untuk(self.unit_smp, self.ta), skema)
        self.assertFalse(Skema._aktif_untuk(self.unit_sma, self.ta))
        skema.action_arsipkan()
        self.assertEqual(skema.state, 'arsip')
        self.assertFalse(Skema._aktif_untuk(self.unit_smp, self.ta))

    def test_salin_tahun_berikut(self):
        TA = self.env['nti_edu.tahun.ajaran']
        ta2 = TA.create({
            'name': 'TA Berikut Tes', 'tanggal_mulai': date(2026, 7, 2), 'tanggal_selesai': date(2027, 6, 30)})
        skema = self._skema(state='aktif', baris=[
            (self.spp, False, False, 100000), (self.spp, self.tingkat_7, self.jurusan, 175000)])
        aksi = skema.action_salin_tahun_berikut()
        baru = self.env['nti_edu.tagihan.skema'].browse(aksi['res_id'])
        self.assertEqual(baru.state, 'draft')
        self.assertEqual(baru.tahun_ajaran_id, ta2)
        self.assertEqual(baru.company_id, self.unit_smp)

        def kunci(skema_):
            return sorted((b.komponen_id.id, b.tingkat_id.id, b.jurusan_id.id, b.nominal)
                          for b in skema_.baris_ids)
        self.assertEqual(kunci(baru), kunci(skema))
        # Tahun ajaran paling akhir tidak punya penerus: galat.
        terakhir = TA.create({
            'name': 'TA Akhir Tes', 'tanggal_mulai': date(2099, 7, 1), 'tanggal_selesai': date(2100, 6, 30)})
        baru = self._skema(ta=terakhir)
        with self.assertRaises(ValidationError):
            baru.action_salin_tahun_berikut()

    def test_potongan_gabung_vs_terbesar(self):
        Potongan = self.env['nti_edu.tagihan.potongan']
        saudara = self._jenis('Saudara', 'persen', 10)
        yatim = self._jenis('Yatim', 'nominal', 50000)
        prestasi = self._jenis('Prestasi', 'persen', 100, gabung=False)
        self._potongan(self.siswa_a, saudara)
        self._potongan(self.siswa_a, yatim)
        hasil = Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000)
        self.assertEqual(sum(j for _x, j in hasil), 70000)
        self.assertEqual({x.id: j for x, j in hasil}, {saudara.id: 20000, yatim.id: 50000})
        self._potongan(self.siswa_a, prestasi)
        hasil = Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000)
        self.assertEqual(hasil, [(prestasi, 200000)])

    def test_potongan_seri_pilih_gabung(self):
        Potongan = self.env['nti_edu.tagihan.potongan']
        a = self._jenis('Gabung', 'nominal', 50000)
        b = self._jenis('Tunggal', 'nominal', 50000, gabung=False)
        self._potongan(self.siswa_a, a)
        self._potongan(self.siswa_a, b)
        self.assertEqual(Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000), [(a, 50000)])

    def test_potongan_pangkas_dan_rentang(self):
        Potongan = self.env['nti_edu.tagihan.potongan']
        j1 = self._jenis('Satu', 'nominal', 150000)
        j2 = self._jenis('Dua', 'nominal', 100000)
        self._potongan(self.siswa_a, j1, selesai=date(2026, 12, 31))
        self._potongan(self.siswa_a, j2, selesai=date(2026, 12, 31))
        hasil = Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000)
        self.assertEqual(sum(j for _x, j in hasil), 200000)
        self.assertEqual([j for _x, j in hasil], [150000, 50000])
        self.assertFalse(Potongan._hitung(self.siswa_a, self.spp, date(2027, 1, 1), 200000))
        self.assertFalse(Potongan._hitung(self.siswa_a, self.spp, date(2026, 6, 30), 200000))
        self.assertFalse(Potongan._hitung(self.siswa_a, self.pangkal, date(2026, 8, 1), 200000))
        self.assertFalse(Potongan._hitung(self.siswa_b, self.spp, date(2026, 8, 1), 200000))

    def test_jenis_tanpa_komponen_tidak_berlaku(self):
        # komponen_ids adalah daftar eksplisit: jenis tanpa komponen tidak berlaku untuk komponen mana pun.
        jenis = self._jenis('Kosong', 'nominal', 1000, komponen=self.env['nti_edu.tagihan.komponen'])
        self._potongan(self.siswa_a, jenis)
        self.assertFalse(self.env['nti_edu.tagihan.potongan']._hitung(
            self.siswa_a, self.spp, date(2026, 8, 1), 200000))

    def test_perlu_persetujuan(self):
        Potongan = self.env['nti_edu.tagihan.potongan']
        jenis = self._jenis('Beasiswa', 'persen', 50, persetujuan=True)
        pot = self._potongan(self.siswa_a, jenis)
        self.assertEqual(pot.state, 'menunggu')
        self.assertFalse(Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000))
        with self.assertRaises(AccessError):
            pot.with_user(self.bendahara_smp).action_setujui()
        pot.with_user(self.admin_keu).action_setujui()
        self.assertEqual(pot.state, 'aktif')
        self.assertEqual(Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000), [(jenis, 100000)])
        pot.with_user(self.bendahara_smp).action_akhiri()
        self.assertEqual(pot.state, 'berakhir')
        self.assertFalse(Potongan._hitung(self.siswa_a, self.spp, date(2026, 8, 1), 200000))

    def test_tolak(self):
        jenis = self._jenis('Beasiswa 2', 'persen', 50, persetujuan=True)
        pot = self._potongan(self.siswa_a, jenis)
        with self.assertRaises(AccessError):
            pot.with_user(self.bendahara_smp).action_tolak()
        pot.with_user(self.admin_keu).action_tolak()
        self.assertEqual(pot.state, 'ditolak')

    def test_potongan_bendahara_dan_penjaga(self):
        jenis = self._jenis('Saudara 2', 'persen', 10)
        Potongan = self.env['nti_edu.tagihan.potongan'].with_user(self.bendahara_smp)
        pot = Potongan.create({
            'siswa_id': self.siswa_a.id, 'jenis_id': jenis.id, 'nilai': 10, 'tanggal_mulai': date(2026, 7, 1)})
        self.assertEqual(pot.company_id, self.unit_smp)
        pot.action_ajukan()
        self.assertEqual(pot.state, 'aktif')
        with self.assertRaises(AccessError):
            pot.write({'nilai': 90})
        with self.assertRaises(AccessError):
            pot.unlink()
        pot.alasan = 'catatan boleh'
        pot.with_user(self.admin_keu).write({'nilai': 20})
        # Siswa unit lain tidak boleh.
        with self.assertRaises(AccessError):
            Potongan.create({
                'siswa_id': self.siswa_c.id, 'jenis_id': jenis.id, 'nilai': 10, 'tanggal_mulai': date(2026, 7, 1)})

    def test_validasi_potongan(self):
        jenis = self._jenis('Saudara 3', 'persen', 10)
        with self.assertRaises(ValidationError):
            self._potongan(self.siswa_a, jenis, nilai=150, aktif=False)
        with self.assertRaises(ValidationError):
            self._potongan(self.siswa_a, jenis, mulai=date(2026, 8, 1), selesai=date(2026, 7, 1), aktif=False)
        with self.assertRaises(ValidationError):
            self.env['nti_edu.tagihan.potongan'].create({
                'siswa_id': self.wali_x.id, 'jenis_id': jenis.id, 'nilai': 5, 'tanggal_mulai': date(2026, 7, 1)})

    def test_isolasi_unit(self):
        jenis = self._jenis('Saudara 4', 'persen', 10)
        pot = self._potongan(self.siswa_a, jenis)
        skema = self._skema(state='aktif')
        Potongan = self.env['nti_edu.tagihan.potongan'].with_user(self.bendahara_sma)
        Skema = self.env['nti_edu.tagihan.skema'].with_user(self.bendahara_sma)
        self.assertFalse(Potongan.search([('id', '=', pot.id)]))
        self.assertFalse(Skema.search([('id', '=', skema.id)]))
        smp = self.env['nti_edu.tagihan.potongan'].with_user(self.pemantau_smp)
        self.assertTrue(smp.search([('id', '=', pot.id)]))
        with self.assertRaises(AccessError):
            smp.browse(pot.id).write({'alasan': 'x'})
