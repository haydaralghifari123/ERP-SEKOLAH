# -*- coding: utf-8 -*-
import base64
from datetime import date, timedelta
from unittest.mock import patch

from odoo import http
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .common import NtiTagihanCommon

# Isi berkas minimal dengan tanda awal (magic bytes) yang benar.
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


@tagged('post_install', '-at_install')
class TestPortal(NtiTagihanCommon, HttpCase):
    """Portal tagihan wali/siswa (spec §4.8): halaman, konfirmasi transfer, PDF; akses hanya ke anak sendiri."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Kata sandi = login: dibutuhkan untuk authenticate pada HttpCase.
        cls.user_wali_x.password = 'tg_wali_x'
        cls.Move = cls.env['account.move']
        cls.Konfirmasi = cls.env['nti_edu.tagihan.konfirmasi']
        cls.spp = cls._buat_komponen('SPP Portal', 'periode_bulanan')
        cls.rekening_smp = cls._buat_rekening(cls.unit_smp)
        cls.rekening_sma = cls._buat_rekening(cls.unit_sma)
        cls.tagihan_a = cls._terbitkan(cls.siswa_a, 210000)
        cls.tagihan_b = cls._terbitkan(cls.siswa_b, 220000)
        cls.tagihan_c = cls._terbitkan(cls.siswa_c, 230000)

    @classmethod
    def _terbitkan(cls, siswa, nominal, periode=date(2026, 8, 1)):
        return cls.Move._nti_edu_terbitkan(
            siswa, cls.spp, nominal, periode, periode + timedelta(days=9), periode=periode)

    def _ada_tagihan(self, teks, tagihan):
        return 'data-tagihan-id="%d"' % tagihan.id in teks

    def _post_konfirmasi(self, tagihan, berkas=('bukti.png', PNG, 'image/png'), **vals):
        data = dict({
            'csrf_token': http.Request.csrf_token(self),
            'tagihan_ids': [str(t.id) for t in tagihan],
            'tanggal_transfer': '2026-08-05',
            'nominal': '210000',
            'rekening_id': str(self.rekening_smp.id),
            'nama_rekening_pengirim': 'Wali X',
            'catatan': 'SPP Agustus',
        }, **vals)
        return self.url_open('/my/tagihan/konfirmasi', data=data, files={'bukti': berkas})

    def _konfirmasi_wali(self):
        return self.Konfirmasi.search([('pengirim_id', '=', self.wali_x.id)])

    # --- halaman tagihan -----------------------------------------------------------------------

    def test_halaman_tagihan(self):
        self.authenticate('tg_wali_x', 'tg_wali_x')
        r = self.url_open('/my/tagihan')
        self.assertEqual(r.status_code, 200)
        # Bawaan: anak pertama menurut nama (Siswa A); pemilih anak memuat kedua anak.
        self.assertTrue(self._ada_tagihan(r.text, self.tagihan_a))
        self.assertIn(self.siswa_a.name, r.text)
        self.assertIn(self.siswa_c.name, r.text)
        self.assertNotIn(self.siswa_b.name, r.text)
        self.assertFalse(self._ada_tagihan(r.text, self.tagihan_b))
        # Rekening tujuan unit tagihan + tombol konfirmasi.
        self.assertIn(self.rekening_smp.nomor, r.text)
        self.assertIn('/my/tagihan/konfirmasi', r.text)

        r = self.url_open('/my/tagihan?siswa=%d' % self.siswa_c.id)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self._ada_tagihan(r.text, self.tagihan_c))
        self.assertFalse(self._ada_tagihan(r.text, self.tagihan_a))
        self.assertFalse(self._ada_tagihan(r.text, self.tagihan_b))
        # Pilihan tersimpan di session.
        self.assertTrue(self._ada_tagihan(self.url_open('/my/tagihan').text, self.tagihan_c))

        for sid in (self.siswa_b.id, self.wali_x.id, 999999):
            self.assertEqual(self.url_open('/my/tagihan?siswa=%d' % sid).status_code, 404, sid)
        self.assertEqual(self.url_open('/my/tagihan?siswa=abc').status_code, 404)

        r = self.url_open('/my')
        self.assertIn('/my/tagihan', r.text)
        self.assertIn('Tagihan', r.text)
        res = self.make_jsonrpc_request('/my/counters', {'counters': ['nti_edu_tagihan_count']})
        self.assertEqual(res['nti_edu_tagihan_count'], 2)

    def test_status_menunggu_dan_lunas(self):
        """Tagihan di konfirmasi menunggu bertanda "Menunggu Verifikasi"; tagihan lunas pindah ke riwayat."""
        lunas = self._terbitkan(self.siswa_a, 50000, date(2026, 7, 1))
        self.env['nti_edu.tagihan.mesin']._bayar(
            lunas, 50000, self.rekening_smp, date(2026, 7, 5), 'Tunai')
        self.Konfirmasi._buat_dari_portal(self.user_wali_x, self.tagihan_a.ids, {
            'tanggal_transfer': date(2026, 8, 5), 'nominal': 210000, 'rekening_id': self.rekening_smp.id,
            'nama_rekening_pengirim': 'Wali X', 'bukti': base64.b64encode(PNG),
            'bukti_nama': 'bukti.png'})
        self.authenticate('tg_wali_x', 'tg_wali_x')
        r = self.url_open('/my/tagihan?siswa=%d' % self.siswa_a.id)
        self.assertIn('Menunggu Verifikasi', r.text)
        self.assertIn('data-menunggu-id="%d"' % self.tagihan_a.id, r.text)
        self.assertIn('data-riwayat-id="%d"' % lunas.id, r.text)
        self.assertIn('data-tagihan-id="%d"' % self.tagihan_a.id, r.text)
        self.assertFalse(self._ada_tagihan(r.text, lunas))

    def test_cicilan_tampil(self):
        aturan = self.env['nti_edu.tagihan.aturan.cicilan'].create({
            'name': 'Cicil 2x Portal', 'maks_kali': 2, 'jarak': 1, 'jarak_satuan': 'bulan'})
        pangkal = self._buat_komponen('Uang Pangkal Portal', 'periode_sekali', aturan_cicilan_id=aturan.id)
        tagihan = self.Move._nti_edu_terbitkan(self.siswa_a, pangkal, 1000000, date(2026, 7, 1), date(2026, 7, 10))
        tagihan._nti_edu_atur_cicilan(2)
        self.authenticate('tg_wali_x', 'tg_wali_x')
        r = self.url_open('/my/tagihan?siswa=%d' % self.siswa_a.id)
        self.assertTrue(self._ada_tagihan(r.text, tagihan))
        self.assertIn('Uang Pangkal Portal', r.text)
        self.assertIn('Cicilan 1:', r.text)
        self.assertIn('Cicilan 2:', r.text)

    def test_anak_lulus_bertunggakan(self):
        self.siswa_c.nti_edu_status = 'lulus'
        siswa_d = self._buat_siswa('Siswa D Lulus Lunas', self.unit_smp, 'TG004', nti_edu_status='lulus')
        self.env['nti_edu.siswa.wali'].create({
            'siswa_id': siswa_d.id, 'partner_id': self.wali_x.id, 'hubungan': 'ayah'})
        self.authenticate('tg_wali_x', 'tg_wali_x')
        r = self.url_open('/my/tagihan')
        self.assertIn(self.siswa_c.name, r.text)
        self.assertNotIn(siswa_d.name, r.text)
        r = self.url_open('/my/tagihan?siswa=%d' % self.siswa_c.id)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self._ada_tagihan(r.text, self.tagihan_c))
        self.assertEqual(self.url_open('/my/tagihan?siswa=%d' % siswa_d.id).status_code, 404)
        self.assertEqual(self.url_open('/my/tagihan/kartu/%d' % siswa_d.id).status_code, 404)

        # Setelah tunggakannya lunas, anak lulus tidak tampil lagi.
        self.env['nti_edu.tagihan.mesin']._bayar(
            self.tagihan_c, 230000, self.rekening_sma, date(2026, 8, 5), 'Tunai')
        r = self.url_open('/my/tagihan')
        self.assertNotIn(self.siswa_c.name, r.text)
        self.assertEqual(self.url_open('/my/tagihan?siswa=%d' % self.siswa_c.id).status_code, 404)
        self.assertEqual(self.url_open('/my/tagihan/invoice/%d' % self.tagihan_c.id).status_code, 404)

    # --- konfirmasi transfer -------------------------------------------------------------------

    def test_kirim_konfirmasi(self):
        self.authenticate('tg_wali_x', 'tg_wali_x')
        r = self.url_open('/my/tagihan/konfirmasi')
        self.assertEqual(r.status_code, 200)
        # Anak di dua unit: pemilih unit; form unit pertama (urut nama: SMA) hanya memuat tagihan dan rekening
        # unit itu.
        self.assertIn('unit=%d' % self.unit_smp.id, r.text)
        self.assertIn('name="tagihan_ids" value="%d"' % self.tagihan_c.id, r.text)
        self.assertNotIn('name="tagihan_ids" value="%d"' % self.tagihan_a.id, r.text)
        self.assertNotIn('name="tagihan_ids" value="%d"' % self.tagihan_b.id, r.text)
        self.assertIn('<option value="%d"' % self.rekening_sma.id, r.text)
        self.assertNotIn('<option value="%d"' % self.rekening_smp.id, r.text)
        r = self.url_open('/my/tagihan/konfirmasi?unit=%d' % self.unit_smp.id)
        self.assertIn('name="tagihan_ids" value="%d"' % self.tagihan_a.id, r.text)
        self.assertNotIn('name="tagihan_ids" value="%d"' % self.tagihan_c.id, r.text)
        self.assertIn('<option value="%d"' % self.rekening_smp.id, r.text)
        self.assertEqual(self.url_open('/my/tagihan/konfirmasi?unit=%d' % self.yayasan.id).status_code, 404)

        r = self._post_konfirmasi(self.tagihan_a)
        self.assertEqual(r.status_code, 200)
        konf = self._konfirmasi_wali()
        self.assertEqual(len(konf), 1)
        self.assertEqual(konf.state, 'menunggu')
        self.assertEqual(konf.tagihan_ids, self.tagihan_a)
        self.assertEqual(konf.nominal, 210000)
        self.assertEqual(konf.bukti_nama, 'bukti.png')
        self.assertEqual(konf.catatan, 'SPP Agustus')
        self.assertIn(konf.name, r.text)  # daftar konfirmasi setelah kirim

        # Tagihan anak orang lain: ditolak di server, tanpa konfirmasi baru; isian sebelumnya dipertahankan.
        r = self._post_konfirmasi(self.tagihan_b, nama_rekening_pengirim='Rekening Ibu Q')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._konfirmasi_wali(), konf)
        with self.subTest('pesan galat'):
            self.assertIn('Tagihan yang dipilih tidak ditemukan atau bukan tagihan anak Anda.', r.text)
        with self.subTest('isian dipertahankan'):
            self.assertIn('value="Rekening Ibu Q"', r.text)

    def test_konfirmasi_berkas_ditolak(self):
        self.unit_smp.nti_edu_bukti_ukuran_maks_mb = 1
        self.authenticate('tg_wali_x', 'tg_wali_x')
        besar = PNG + b'\x00' * (1024 * 1024)
        # Pesan galat persis (bukan teks bantuan/label form yang selalu tampil).
        for nama, kiriman, pesan in (
                ('terlalu besar', {'berkas': ('besar.png', besar, 'image/png')},
                 'Ukuran bukti transfer melebihi batas 1 MB.'),
                ('jenis salah', {'berkas': ('bukti.txt', b'teks biasa', 'text/plain')},
                 'Bukti transfer harus berkas JPG, PNG, atau PDF.'),
                ('nominal salah', {'nominal': 'abc'}, 'Nominal transfer tidak valid.')):
            with self.subTest(nama):
                r = self._post_konfirmasi(self.tagihan_a, **kiriman)
                self.assertEqual(r.status_code, 200)
                self.assertIn(pesan, r.text)
        # Tanpa token CSRF: ditolak.
        with mute_logger('odoo.http'):
            r = self.url_open('/my/tagihan/konfirmasi', data={'tagihan_ids': str(self.tagihan_a.id)},
                              files={'bukti': ('bukti.png', PNG, 'image/png')})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self._konfirmasi_wali())

    def test_konfirmasi_access_error_tidak_bocor(self):
        """AccessError dari server tidak ditampilkan apa adanya di portal; diganti pesan umum."""
        Konfirmasi = type(self.env['nti_edu.tagihan.konfirmasi'])

        def _gagal(*args, **kwargs):
            raise AccessError('RAHASIA_INTERNAL model account.move id 42')

        self.authenticate('tg_wali_x', 'tg_wali_x')
        with patch.object(Konfirmasi, '_buat_dari_portal', _gagal):
            r = self._post_konfirmasi(self.tagihan_a)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('RAHASIA_INTERNAL', r.text)
        self.assertIn('Konfirmasi transfer tidak dapat diproses', r.text)
        self.assertFalse(self._konfirmasi_wali())

    def test_konfirmasi_ditolak_tampil(self):
        konf = self.Konfirmasi._buat_dari_portal(self.user_wali_x, self.tagihan_a.ids, {
            'tanggal_transfer': date(2026, 8, 5), 'nominal': 210000, 'rekening_id': self.rekening_smp.id,
            'nama_rekening_pengirim': 'Wali X', 'bukti': base64.b64encode(PNG),
            'bukti_nama': 'bukti.png'})
        alasan = self.env.ref('nti_edu_tagihan.alasan_tolak_lainnya')
        konf.with_user(self.bendahara_smp)._tolak(alasan, 'Bukti buram sekali')
        self.authenticate('tg_wali_x', 'tg_wali_x')
        r = self.url_open('/my/tagihan?siswa=%d' % self.siswa_a.id)
        self.assertIn(konf.name, r.text)
        self.assertIn('Ditolak', r.text)
        self.assertIn(alasan.name, r.text)
        self.assertIn('Bukti buram sekali', r.text)

    # --- PDF -----------------------------------------------------------------------------------

    def test_pdf_akses(self):
        self.authenticate('tg_wali_x', 'tg_wali_x')
        for url in ('/my/tagihan/kartu/%d' % self.siswa_a.id,
                    '/my/tagihan/kartu/%d?tahun=%d' % (self.siswa_c.id, self.ta.id),
                    '/my/tagihan/invoice/%d' % self.tagihan_a.id,
                    '/my/tagihan/invoice/%d' % self.tagihan_c.id):
            r = self.url_open(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertEqual(r.headers['Content-Type'], 'application/pdf', url)
        for url in ('/my/tagihan/kartu/%d' % self.siswa_b.id,
                    '/my/tagihan/kartu/%d' % self.wali_x.id,
                    '/my/tagihan/kartu/%d?tahun=999999' % self.siswa_a.id,
                    '/my/tagihan/invoice/%d' % self.tagihan_b.id,
                    '/my/tagihan/invoice/999999'):
            self.assertEqual(self.url_open(url).status_code, 404, url)

    # --- siswa ber-akun portal -----------------------------------------------------------------

    def test_siswa_portal(self):
        user = new_test_user(
            self.env, login='tg_siswa_b', groups='base.group_portal', password='tg_siswa_b',
            company_id=self.unit_smp.id, company_ids=[(6, 0, self.unit_smp.ids)])
        user.partner_id = self.siswa_b
        self.authenticate('tg_siswa_b', 'tg_siswa_b')
        r = self.url_open('/my/tagihan')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self._ada_tagihan(r.text, self.tagihan_b))
        self.assertFalse(self._ada_tagihan(r.text, self.tagihan_a))
        self.assertNotIn(self.siswa_a.name, r.text)
        self.assertEqual(self.url_open('/my/tagihan?siswa=%d' % self.siswa_a.id).status_code, 404)
        self.assertEqual(self.url_open('/my/tagihan/invoice/%d' % self.tagihan_a.id).status_code, 404)
        self.assertEqual(self.url_open('/my/tagihan/invoice/%d' % self.tagihan_b.id).status_code, 200)
        r = self.url_open('/my/tagihan/konfirmasi')
        self.assertIn('name="tagihan_ids" value="%d"' % self.tagihan_b.id, r.text)
        self.assertNotIn('name="tagihan_ids" value="%d"' % self.tagihan_a.id, r.text)
