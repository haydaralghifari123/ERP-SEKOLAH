# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import freeze_time, tagged
from odoo.tools import mute_logger

from .common import NtiTagihanCommon

LOGGER_MESIN = 'odoo.addons.nti_edu_tagihan.models.mesin'


@tagged('post_install', '-at_install')
class TestMesin(NtiTagihanCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.Mesin = cls.env['nti_edu.tagihan.mesin']
        cls.Move = cls.env['account.move']
        cls.Wizard = cls.env['nti_edu.tagihan.buat.wizard']
        cls.juni = ref('nti_edu_tagihan.bulan_06')
        Periode = cls.env['nti_edu.tagihan.periode.jenis']
        cls.periode_bulanan = Periode.create({
            'name': 'Bulanan Mesin', 'dasar': 'bulan', 'jumlah_bulan': 1, 'hari_terbit': 1,
            'hari_jatuh_tempo': 10, 'bulan_libur_ids': [(6, 0, cls.juni.ids)]})
        cls.periode_semester = Periode.create({
            'name': 'Semester Mesin', 'dasar': 'semester', 'hari_terbit': 1, 'hari_jatuh_tempo': 15})
        cls.periode_sekali = Periode.create({
            'name': 'Sekali Mesin', 'dasar': 'sekali', 'hari_terbit': 1, 'hari_jatuh_tempo': 30})
        cls.spp = cls._buat_komponen('SPP Mesin', None, periode_jenis_id=cls.periode_bulanan.id)
        cls.kegiatan = cls._buat_komponen('Kegiatan Mesin', None, periode_jenis_id=cls.periode_semester.id)
        cls.pangkal = cls._buat_komponen('Pangkal Mesin', None, periode_jenis_id=cls.periode_sekali.id)
        cls.tingkat_7 = ref('nti_edu_base.tingkat_smp_7')
        cls.tingkat_8 = ref('nti_edu_base.tingkat_smp_8')
        cls.skema = cls.env['nti_edu.tagihan.skema'].create({
            'company_id': cls.unit_smp.id, 'tahun_ajaran_id': cls.ta.id, 'state': 'aktif',
            'baris_ids': [
                (0, 0, {'komponen_id': cls.spp.id, 'tingkat_id': cls.tingkat_7.id, 'nominal': 150000}),
                (0, 0, {'komponen_id': cls.spp.id, 'tingkat_id': cls.tingkat_8.id, 'nominal': 175000}),
                (0, 0, {'komponen_id': cls.kegiatan.id, 'nominal': 600000}),
                (0, 0, {'komponen_id': cls.pangkal.id, 'tingkat_id': cls.tingkat_7.id, 'nominal': 1000000}),
            ]})
        cls.unit_smp.write({'nti_edu_tagihan_mulai': date(2026, 7, 1), 'nti_edu_tagihan_otomatis': True})

    # --- bantuan ---------------------------------------------------------------------------

    def _tagihan(self, siswa, komponen):
        return self.Move.search([
            ('nti_edu_siswa_id', '=', siswa.id), ('nti_edu_komponen_id', '=', komponen.id),
            ('state', '!=', 'cancel')], order='nti_edu_periode')

    def _info(self, komponen, periode):
        for info in self.Mesin._periode_dalam_tahun(komponen, self.ta):
            if info['periode'] == periode:
                return info
        raise AssertionError('Periode %s tidak ditemukan' % periode)

    def _siswa_baru(self, nama, nis, tanggal_masuk, rombel=None):
        siswa = self._buat_siswa(nama, self.unit_smp, nis)
        self._masukkan(siswa, rombel or self.rombel_7a, tanggal_masuk)
        return siswa

    def _wizard_vals(self, **vals):
        return dict({
            'company_id': self.unit_smp.id, 'komponen_id': self.spp.id, 'tahun_ajaran_id': self.ta.id,
            'periode': date(2026, 8, 1), 'rombel_ids': [(6, 0, self.rombel_7a.ids)]}, **vals)

    # --- periode ---------------------------------------------------------------------------

    def test_periode_bulanan_libur(self):
        infos = self.Mesin._periode_dalam_tahun(self.spp, self.ta)
        self.assertEqual(
            [i['periode'] for i in infos],
            [date(2026, b, 1) for b in range(7, 13)] + [date(2027, b, 1) for b in range(1, 6)])
        juli = infos[0]
        self.assertEqual(juli['akhir'], date(2026, 7, 31))
        self.assertEqual(juli['terbit'], date(2026, 7, 1))
        self.assertEqual(juli['jatuh_tempo'], date(2026, 7, 10))
        self.assertEqual(juli['semester'], self.semester_ganjil)
        self.assertEqual(infos[6]['semester'], self.semester_genap)

        triwulan = self.env['nti_edu.tagihan.periode.jenis'].create({
            'name': 'Triwulan Mesin', 'dasar': 'bulan', 'jumlah_bulan': 3, 'hari_terbit': 5,
            'hari_jatuh_tempo': 20, 'bulan_libur_ids': [(6, 0, self.juni.ids)]})
        komponen = self._buat_komponen('Triwulan Mesin', None, periode_jenis_id=triwulan.id)
        infos = self.Mesin._periode_dalam_tahun(komponen, self.ta)
        self.assertEqual([i['periode'] for i in infos],
                         [date(2026, 7, 1), date(2026, 10, 1), date(2027, 1, 1), date(2027, 4, 1)])
        self.assertEqual(infos[0]['akhir'], date(2026, 9, 30))
        self.assertEqual(infos[-1]['akhir'], date(2027, 6, 30))
        self.assertEqual(infos[1]['terbit'], date(2026, 10, 5))
        self.assertEqual(infos[1]['jatuh_tempo'], date(2026, 10, 20))

        semester = self.Mesin._periode_dalam_tahun(self.kegiatan, self.ta)
        self.assertEqual([(i['periode'], i['akhir'], i['semester']) for i in semester], [
            (date(2026, 7, 1), date(2026, 12, 31), self.semester_ganjil),
            (date(2027, 1, 1), date(2027, 6, 30), self.semester_genap)])
        self.assertEqual(semester[1]['jatuh_tempo'], date(2027, 1, 15))

        tahunan = self._buat_komponen('Tahunan Mesin', 'periode_tahunan')
        infos = self.Mesin._periode_dalam_tahun(tahunan, self.ta)
        self.assertEqual(len(infos), 1)
        self.assertEqual((infos[0]['periode'], infos[0]['akhir']), (date(2026, 7, 1), date(2027, 6, 30)))

        sekali = self.Mesin._periode_dalam_tahun(self.pangkal, self.ta)
        self.assertEqual(len(sekali), 1)
        self.assertFalse(sekali[0]['periode'])
        self.assertEqual(sekali[0]['terbit'], date(2026, 7, 1))
        self.assertEqual(sekali[0]['jatuh_tempo'], date(2026, 7, 31))

    def test_jatuh_tempo_dipangkas(self):
        periode = self.env['nti_edu.tagihan.periode.jenis'].create({
            'name': 'Akhir Bulan', 'dasar': 'bulan', 'jumlah_bulan': 1, 'hari_jatuh_tempo': 31})
        komponen = self._buat_komponen('SPP Akhir Bulan', None, periode_jenis_id=periode.id)
        self.assertEqual(self._info(komponen, date(2027, 2, 1))['jatuh_tempo'], date(2027, 2, 28))
        self.assertEqual(self._info(komponen, date(2026, 9, 1))['jatuh_tempo'], date(2026, 9, 30))
        self.assertEqual(self._info(komponen, date(2026, 7, 1))['jatuh_tempo'], date(2026, 7, 31))
        with self.assertRaises(ValidationError):
            periode.hari_jatuh_tempo = 32

    # --- rencana ---------------------------------------------------------------------------

    def test_siswa_masuk_tengah_bulanan(self):
        siswa = self._siswa_baru('Siswa Masuk September', 'TGM01', date(2026, 9, 15))
        self.spp.aturan_masuk_id = self.env.ref('nti_edu_tagihan.aturan_masuk_berikutnya')
        self.Mesin._terbitkan(self.unit_smp, self.spp, self._info(self.spp, date(2026, 8, 1)))
        hasil = self.Mesin._terbitkan(self.unit_smp, self.spp, self._info(self.spp, date(2026, 9, 1)))
        tagihan = self._tagihan(siswa, self.spp)
        # Periode satu bulan: aturan masuk tidak berlaku, selalu mulai bulan masuk dan ditagih penuh.
        self.assertEqual(tagihan.mapped('nti_edu_periode'), [date(2026, 9, 1)])
        self.assertEqual(tagihan.amount_total, 150000)
        self.assertIn(tagihan, hasil['buat'])
        self.assertEqual(self._tagihan(self.siswa_a, self.spp).mapped('nti_edu_periode'),
                         [date(2026, 8, 1), date(2026, 9, 1)])

    def test_masuk_tengah_semester(self):
        siswa = self._siswa_baru('Siswa Masuk Oktober', 'TGM02', date(2026, 10, 1))
        ganjil = self._info(self.kegiatan, date(2026, 7, 1))
        genap = self._info(self.kegiatan, date(2027, 1, 1))
        ref = self.env.ref
        for xmlid, harapan in (('aturan_masuk_penuh', 600000), ('aturan_masuk_berikutnya', None),
                               ('aturan_masuk_prorata', 300000)):
            self.kegiatan.aturan_masuk_id = ref('nti_edu_tagihan.%s' % xmlid)
            rencana = self.Mesin._rencana(self.unit_smp, self.kegiatan, ganjil)
            baris = [b for b in rencana['buat'] if b['siswa'] == siswa]
            if harapan is None:
                self.assertFalse(baris, xmlid)
                self.assertNotIn(siswa, [s for s, _alasan in rencana['lewati']])
            else:
                self.assertEqual(baris[0]['nominal'], harapan, xmlid)
            # Siswa yang masuk sejak awal selalu penuh; periode berikutnya selalu penuh.
            awal = [b for b in rencana['buat'] if b['siswa'] == self.siswa_a]
            self.assertEqual(awal[0]['nominal'], 600000)
            lanjut = [b for b in self.Mesin._rencana(self.unit_smp, self.kegiatan, genap)['buat']
                      if b['siswa'] == siswa]
            self.assertEqual(lanjut[0]['nominal'], 600000)

        hasil = self.Mesin._terbitkan(self.unit_smp, self.kegiatan, ganjil)
        tagihan = self._tagihan(siswa, self.kegiatan)
        self.assertIn(tagihan, hasil['buat'])
        self.assertEqual(tagihan.amount_total, 300000)
        self.assertEqual(tagihan.nti_edu_semester_id, self.semester_ganjil)

    def test_prorata_dibulatkan_rupiah(self):
        # Spec §4.2: prorata dibulatkan ke rupiah utuh, bukan ke sen. 500.000 × 4/6 = 333.333,33 → 333.333.
        self.skema.baris_ids.filtered(lambda b: b.komponen_id == self.kegiatan).nominal = 500000
        self.kegiatan.aturan_masuk_id = self.env.ref('nti_edu_tagihan.aturan_masuk_prorata')
        siswa = self._siswa_baru('Siswa Masuk September Prorata', 'TGM04', date(2026, 9, 10))
        ganjil = self._info(self.kegiatan, date(2026, 7, 1))
        baris = [b for b in self.Mesin._rencana(self.unit_smp, self.kegiatan, ganjil)['buat'] if b['siswa'] == siswa]
        self.assertEqual(baris[0]['nominal'], 333333)
        self.Mesin._terbitkan(self.unit_smp, self.kegiatan, ganjil)
        self.assertEqual(self._tagihan(siswa, self.kegiatan).amount_total, 333333)

    def test_cron_commit_per_unit_kerja(self):
        # Jalur cron sungguhan commit setelah tiap (unit, komponen, periode); di tes `_boleh_commit` palsu.
        with patch('odoo.addons.nti_edu_tagihan.models.mesin._boleh_commit', return_value=True), \
                patch.object(self.env.cr, 'commit') as commit:
            self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 2))
        # SPP Jul + Agu, kegiatan ganjil, pangkal sekali = 4 unit kerja untuk unit SMP.
        self.assertEqual(commit.call_count, 4)
        self.assertEqual(len(self._tagihan(self.siswa_a, self.spp)), 2)
        # Tanpa tambalan, tes tidak pernah commit.
        with patch.object(self.env.cr, 'commit') as commit:
            self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 9, 2))
        commit.assert_not_called()

    def test_tagihan_mulai(self):
        self.unit_smp.nti_edu_tagihan_mulai = date(2026, 11, 1)
        baru = self._siswa_baru('Siswa Masuk November', 'TGM03', date(2026, 11, 5))
        with freeze_time('2026-11-02'):
            self.Mesin._cron_buat_tagihan()
        self.assertEqual(self._tagihan(self.siswa_a, self.spp).mapped('nti_edu_periode'), [date(2026, 11, 1)])
        self.assertEqual(self._tagihan(self.siswa_b, self.spp).mapped('nti_edu_periode'), [date(2026, 11, 1)])
        self.assertEqual(self._tagihan(baru, self.spp).mapped('nti_edu_periode'), [date(2026, 11, 1)])
        # Semester ganjil dimulai sebelum tagihan_mulai: tidak ditagih.
        self.assertFalse(self._tagihan(self.siswa_a, self.kegiatan))
        # Uang pangkal: siswa lama (masuk 2026-07-01) tidak; siswa baru ya, terbit pada tanggal masuknya.
        self.assertFalse(self._tagihan(self.siswa_a, self.pangkal))
        pangkal = self._tagihan(baru, self.pangkal)
        self.assertEqual(len(pangkal), 1)
        self.assertFalse(pangkal.nti_edu_periode)
        self.assertEqual(pangkal.amount_total, 1000000)
        self.assertEqual(pangkal.invoice_date, date(2026, 11, 5))
        self.assertEqual(pangkal.invoice_date_due, date(2026, 12, 5))
        # Wizard juga tidak pernah menerbitkan periode sebelum tagihan_mulai.
        wizard = self.Wizard.with_user(self.bendahara_smp).create(self._wizard_vals())
        self.assertEqual(wizard.jumlah_siswa, 0)
        with self.assertRaisesRegex(UserError, 'Tagihan Mulai'):
            wizard.action_terbitkan()
        self.assertFalse(self._tagihan(self.siswa_a, self.spp).filtered(
            lambda t: t.nti_edu_periode == date(2026, 8, 1)))

    def test_cron_idempoten(self):
        siswa = self.siswa_a | self.siswa_b
        with freeze_time('2026-08-02'):
            self.Mesin._cron_buat_tagihan()
        semua = self.Move.search([('nti_edu_siswa_id', 'in', siswa.ids)])
        # SPP Jul+Agu untuk A dan B, kegiatan ganjil untuk A dan B, pangkal hanya tingkat VII (A).
        self.assertEqual(len(semua), 7)
        self.assertEqual(self._tagihan(self.siswa_a, self.spp).mapped('nti_edu_periode'),
                         [date(2026, 7, 1), date(2026, 8, 1)])
        self.assertFalse(self._tagihan(self.siswa_b, self.pangkal))
        with freeze_time('2026-08-02'):
            self.Mesin._cron_buat_tagihan()
        self.assertEqual(self.Move.search_count([('nti_edu_siswa_id', 'in', siswa.ids)]), 7)

        # Galat satu siswa tidak menghentikan siswa lain dan dilaporkan di `lewati`.
        Move = type(self.Move)
        asli = Move._nti_edu_terbitkan
        uji = self

        def terbitkan_galat(self_move, siswa_tagih, *args, **kwargs):
            if siswa_tagih == uji.siswa_b:
                raise UserError('Galat buatan untuk siswa B')
            return asli(self_move, siswa_tagih, *args, **kwargs)

        with patch.object(Move, '_nti_edu_terbitkan', terbitkan_galat), mute_logger(LOGGER_MESIN):
            hasil = self.Mesin._terbitkan(self.unit_smp, self.spp, self._info(self.spp, date(2026, 9, 1)))
            self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 10, 2))
        self.assertEqual(hasil['buat'].nti_edu_siswa_id, self.siswa_a)
        self.assertIn((self.siswa_b, 'Galat buatan untuk siswa B'), hasil['lewati'])
        self.assertEqual(self._tagihan(self.siswa_a, self.spp).mapped('nti_edu_periode')[-2:],
                         [date(2026, 9, 1), date(2026, 10, 1)])
        self.assertEqual(self._tagihan(self.siswa_b, self.spp).mapped('nti_edu_periode'),
                         [date(2026, 7, 1), date(2026, 8, 1)])

        # Komponen yang rusak tidak menghentikan komponen lain.
        Mesin = type(self.Mesin)
        rencana_asli = Mesin._rencana

        def rencana_galat(self_mesin, company, komponen, info, rombel=None):
            if komponen == uji.spp:
                raise ValueError('Komponen rusak')
            return rencana_asli(self_mesin, company, komponen, info, rombel=rombel)

        with patch.object(Mesin, '_rencana', rencana_galat), mute_logger(LOGGER_MESIN):
            self.Mesin._cron_buat_tagihan(hari_ini=date(2027, 1, 2))
        self.assertEqual(self._tagihan(self.siswa_a, self.kegiatan).mapped('nti_edu_periode'),
                         [date(2026, 7, 1), date(2027, 1, 1)])
        self.assertEqual(self._tagihan(self.siswa_b, self.spp).mapped('nti_edu_periode'),
                         [date(2026, 7, 1), date(2026, 8, 1)])

        # Setelah galat hilang, jadwal melengkapi tagihan yang tertinggal.
        self.Mesin._cron_buat_tagihan(hari_ini=date(2027, 1, 2))
        self.assertEqual(len(self._tagihan(self.siswa_b, self.spp)), 7)

    def test_unit_tanpa_otomatis(self):
        self.unit_smp.nti_edu_tagihan_otomatis = False
        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 2))
        self.assertFalse(self.Move.search([('nti_edu_siswa_id', '=', self.siswa_a.id)]))

    def test_siswa_nonaktif_dilewati(self):
        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 8, 2))
        lama = self._tagihan(self.siswa_b, self.spp)
        self.assertEqual(len(lama), 2)
        with freeze_time('2026-09-20'):
            self.siswa_b.nti_edu_status = 'pindah'
        self.Mesin._cron_buat_tagihan(hari_ini=date(2026, 10, 2))
        self.assertEqual(self._tagihan(self.siswa_b, self.spp), lama)
        self.assertEqual(set(lama.mapped('state')), {'posted'})
        self.assertEqual(len(self._tagihan(self.siswa_a, self.spp)), 4)

    def test_tingkat_berbeda(self):
        info = self._info(self.spp, date(2026, 8, 1))
        hasil = self.Mesin._terbitkan(self.unit_smp, self.spp, info)
        self.assertFalse(hasil['lewati'])
        tagihan_a = hasil['buat'].filtered(lambda t: t.nti_edu_siswa_id == self.siswa_a)
        tagihan_b = hasil['buat'].filtered(lambda t: t.nti_edu_siswa_id == self.siswa_b)
        self.assertEqual(tagihan_a.amount_total, 150000)
        self.assertEqual(tagihan_b.amount_total, 175000)
        self.assertEqual(tagihan_a.nti_edu_rombel_id, self.rombel_7a)
        self.assertEqual(tagihan_b.nti_edu_rombel_id, self.rombel_8a)
        self.assertEqual(tagihan_a.nti_edu_tahun_ajaran_id, self.ta)
        self.assertEqual(tagihan_a.nti_edu_semester_id, self.semester_ganjil)
        self.assertEqual(tagihan_a.nti_edu_periode, date(2026, 8, 1))
        self.assertEqual(tagihan_a.invoice_date, date(2026, 8, 1))
        self.assertEqual(tagihan_a.invoice_date_due, date(2026, 8, 10))
        self.assertEqual(tagihan_a.state, 'posted')
        # Siswa unit lain tidak ikut.
        self.assertFalse(self._tagihan(self.siswa_c, self.spp))

    def test_wizard_pratinjau_dan_lewati(self):
        Wizard = self.Wizard.with_user(self.bendahara_smp)
        bawaan = Wizard.create({'komponen_id': self.spp.id})
        self.assertEqual(bawaan.company_id, self.unit_smp)
        self.assertEqual(bawaan.tahun_ajaran_id, self.ta)

        wizard = Wizard.create(self._wizard_vals())
        self.assertEqual(wizard.jumlah_siswa, 1)
        self.assertEqual(wizard.total, 150000)
        self.assertFalse(wizard.daftar_lewati)
        aksi = wizard.action_terbitkan()
        self.assertEqual(aksi['type'], 'ir.actions.client')
        self.assertEqual(self._tagihan(self.siswa_a, self.spp).mapped('nti_edu_periode'), [date(2026, 8, 1)])
        self.assertFalse(self._tagihan(self.siswa_b, self.spp))

        ulang = Wizard.create(self._wizard_vals())
        self.assertEqual(ulang.jumlah_siswa, 0)
        self.assertIn(self.siswa_a.name, ulang.daftar_lewati)
        self.assertIn('sudah ditagih', ulang.daftar_lewati)
        ulang.action_terbitkan()
        self.assertEqual(len(self._tagihan(self.siswa_a, self.spp)), 1)

        # Periode harus salah satu awal periode komponen; komponen sekali tanpa periode.
        for salah in (date(2026, 8, 15), date(2027, 6, 1), date(2027, 7, 1)):
            with self.assertRaises(ValidationError):
                Wizard.create(self._wizard_vals(periode=salah))
        with self.assertRaises(ValidationError):
            Wizard.create(self._wizard_vals(komponen_id=self.pangkal.id))
        pangkal = Wizard.create(self._wizard_vals(komponen_id=self.pangkal.id, periode=False))
        self.assertEqual(pangkal.jumlah_siswa, 1)
        self.assertEqual(pangkal.total, 1000000)

        # Hak: pemantau tidak boleh menerbitkan; bendahara unit lain tidak boleh untuk SMP.
        wizard_su = self.Wizard.create(self._wizard_vals(periode=date(2026, 9, 1)))
        with self.assertRaises(AccessError):
            wizard_su.with_user(self.pemantau_smp).action_terbitkan()
        wizard_sma = self.Wizard.with_user(self.bendahara_sma).create(
            self._wizard_vals(periode=date(2026, 9, 1), rombel_ids=False))
        self.assertEqual(wizard_sma.jumlah_siswa, 0)
        with self.assertRaises(AccessError):
            wizard_sma.action_terbitkan()
        self.assertFalse(self._tagihan(self.siswa_a, self.spp).filtered(
            lambda t: t.nti_edu_periode == date(2026, 9, 1)))

    def test_potongan_diterapkan(self):
        self.skema.baris_ids.filtered(
            lambda b: b.komponen_id == self.spp and b.tingkat_id == self.tingkat_7).nominal = 200000
        jenis = self.env['nti_edu.tagihan.potongan.jenis'].create({
            'name': 'Saudara Mesin', 'tipe': 'persen', 'nilai_bawaan': 10,
            'komponen_ids': [(6, 0, self.spp.ids)]})
        potongan = self.env['nti_edu.tagihan.potongan'].create({
            'siswa_id': self.siswa_a.id, 'jenis_id': jenis.id, 'tanggal_mulai': date(2026, 7, 1)})
        potongan.action_ajukan()
        self.assertEqual(potongan.state, 'aktif')
        wizard = self.Wizard.with_user(self.bendahara_smp).create(self._wizard_vals())
        self.assertEqual(wizard.total, 180000)
        self.Mesin._terbitkan(self.unit_smp, self.spp, self._info(self.spp, date(2026, 8, 1)))
        tagihan = self._tagihan(self.siswa_a, self.spp)
        self.assertEqual(tagihan.amount_total, 180000)
        minus = tagihan.invoice_line_ids.filtered(lambda b: b.price_subtotal < 0)
        self.assertEqual(minus.price_subtotal, -20000)
        self.assertEqual(minus.name, 'Potongan Saudara Mesin')
