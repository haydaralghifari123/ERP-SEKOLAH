# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, fields, models
from odoo.tools import format_date

GRUP_PEMANTAU = 'nti_edu_tagihan.group_tagihan_pemantau'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nti_edu_saldo_kredit = fields.Monetary(
        string='Saldo Kredit', compute='_compute_nti_edu_saldo_kredit', currency_field='currency_id',
        groups=GRUP_PEMANTAU,
        help='Pembayaran atau nota kredit siswa yang belum terpakai untuk tagihan (kredit piutang terbuka).')
    nti_edu_tagihan_ids = fields.Many2many(
        'account.move', string='Daftar Tagihan', compute='_compute_nti_edu_tagihan_ids', groups=GRUP_PEMANTAU,
        help='Tagihan sekolah siswa (tidak termasuk yang dibatalkan) yang boleh Anda lihat.')
    nti_edu_sisa_tagihan = fields.Monetary(
        string='Sisa Tagihan', compute='_compute_nti_edu_ringkasan_tagihan', currency_field='currency_id',
        groups=GRUP_PEMANTAU, help='Total sisa seluruh tagihan sekolah siswa yang belum lunas, di semua unit.')
    nti_edu_tunggakan = fields.Monetary(
        string='Tunggakan', compute='_compute_nti_edu_ringkasan_tagihan', currency_field='currency_id',
        groups=GRUP_PEMANTAU, help='Bagian sisa tagihan (per cicilan) yang sudah lewat jatuh tempo, di semua unit.')
    nti_edu_potongan_ids = fields.Many2many(
        'nti_edu.tagihan.potongan', string='Potongan Aktif', compute='_compute_nti_edu_potongan_ids',
        groups=GRUP_PEMANTAU)

    def _compute_nti_edu_saldo_kredit(self):
        # Dibaca sebagai superuser: saldo siswa mencakup kredit dari dokumen di luar cakupan pembukuan pembaca.
        siswa = self.filtered(lambda p: p._origin.id and p.nti_edu_is_siswa)
        saldo = {}
        if siswa:
            data = self.env['account.move.line'].sudo()._read_group([
                ('partner_id', 'in', siswa._origin.ids),
                ('account_type', '=', 'asset_receivable'),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('balance', '<', 0.0),
            ], ['partner_id'], ['amount_residual:sum'])
            saldo = {partner.id: -total for partner, total in data}
        for partner in self:
            partner.nti_edu_saldo_kredit = saldo.get(partner._origin.id, 0.0)

    def _compute_nti_edu_tagihan_ids(self):
        # Dengan hak pembaca: daftar ini dibuka sebagai dokumen, jadi hanya tagihan yang boleh dibaca yang tampil.
        siswa = self.filtered(lambda p: p._origin.id and p.nti_edu_is_siswa)
        per_siswa = {}
        if siswa:
            for tagihan in self.env['account.move'].search([
                    ('move_type', '=', 'out_invoice'), ('nti_edu_is_tagihan', '=', True),
                    ('nti_edu_siswa_id', 'in', siswa._origin.ids), ('state', '!=', 'cancel')],
                    order='invoice_date desc, id desc'):
                per_siswa.setdefault(tagihan.nti_edu_siswa_id.id, []).append(tagihan.id)
        for partner in self:
            partner.nti_edu_tagihan_ids = [(6, 0, per_siswa.get(partner._origin.id, []))]

    def _compute_nti_edu_ringkasan_tagihan(self):
        # Ringkasan siswa dibaca sebagai superuser (seperti saldo kredit): termasuk tunggakan di unit lama siswa.
        hari_ini = fields.Date.context_today(self)
        siswa = self.filtered(lambda p: p._origin.id and p.nti_edu_is_siswa)
        sisa, tunggakan = {}, {}
        if siswa:
            baris = self.env['account.move.line'].sudo().search([
                ('move_id.move_type', '=', 'out_invoice'), ('move_id.nti_edu_is_tagihan', '=', True),
                ('move_id.nti_edu_siswa_id', 'in', siswa._origin.ids), ('parent_state', '=', 'posted'),
                ('account_id.account_type', '=', 'asset_receivable'), ('reconciled', '=', False),
            ])
            for b in baris:
                kunci = b.move_id.nti_edu_siswa_id.id
                sisa[kunci] = sisa.get(kunci, 0.0) + b.amount_residual
                if b.date_maturity and b.date_maturity < hari_ini:
                    tunggakan[kunci] = tunggakan.get(kunci, 0.0) + b.amount_residual
        for partner in self:
            partner.nti_edu_sisa_tagihan = sisa.get(partner._origin.id, 0.0)
            partner.nti_edu_tunggakan = tunggakan.get(partner._origin.id, 0.0)

    def _compute_nti_edu_potongan_ids(self):
        siswa = self.filtered(lambda p: p._origin.id and p.nti_edu_is_siswa)
        per_siswa = {}
        if siswa:
            for potongan in self.env['nti_edu.tagihan.potongan'].search([
                    ('siswa_id', 'in', siswa._origin.ids), ('state', '=', 'aktif')]):
                per_siswa.setdefault(potongan.siswa_id.id, []).append(potongan.id)
        for partner in self:
            partner.nti_edu_potongan_ids = [(6, 0, per_siswa.get(partner._origin.id, []))]

    # --- penerima email ----------------------------------------------------------------------

    def _nti_edu_peta_penerima_tagihan(self):
        """Penerima email tagihan per siswa (spec §4.9): `{id siswa: partner penerima}`. Per siswa: wali penanggung
        biaya yang aktif dan punya email; bila tidak ada, wali kontak utama yang aktif dan punya email; bila tidak
        ada, kosong. Baris wali dibaca sebagai superuser dalam satu pencarian; hasil dalam env pemanggil."""
        siswa = self.sudo().filtered('nti_edu_is_siswa')
        hasil = {s.id: self.browse() for s in siswa}
        if not siswa:
            return hasil
        semua = self.env['nti_edu.siswa.wali'].sudo().search([
            ('siswa_id', 'in', siswa.ids), ('partner_id.active', '=', True), ('partner_id.email', '!=', False),
        ]).filtered(lambda w: (w.partner_id.email or '').strip())
        per_siswa = {}
        for baris in semua:
            per_siswa[baris.siswa_id.id] = per_siswa.get(baris.siswa_id.id, baris.browse()) | baris
        for siswa_id, baris in per_siswa.items():
            pilihan = baris.filtered('is_penanggung_biaya') or baris.filtered('is_kontak_utama')
            hasil[siswa_id] = pilihan.partner_id.with_env(self.env)
        return hasil

    def _nti_edu_penerima_tagihan(self):
        """Gabungan penerima email tagihan siswa-siswa ini (lihat `_nti_edu_peta_penerima_tagihan`)."""
        penerima = self.browse()
        for partner in self._nti_edu_peta_penerima_tagihan().values():
            penerima |= partner
        return penerima

    # --- kartu SPP ---------------------------------------------------------------------------

    def _nti_edu_data_kartu_spp(self, tahun_ajaran):
        """Data Kartu SPP siswa ini untuk `tahun_ajaran` (spec §4.7), dibaca sebagai superuser; pemanggil wajib
        memeriksa hak akses lebih dahulu (laporan Kartu SPP, portal).

        Tagihan yang dihitung: tagihan sekolah terbit (bukan batal) milik tahun ajaran itu — menurut tahun ajaran
        tagihan, tahun ajaran tagihan asal (denda), atau tanggal periode/terbit bila tanpa tahun ajaran.

        - `bulan`: 12 tanggal awal bulan tahun ajaran, mulai bulan tanggal mulainya.
        - `bulanan`: per komponen berperiode 1 bulan: `komponen` dan `sel` (12 sel, urut `bulan`; tiap sel juga
          memuat `bulan` dan `nama_bulan`).
        - `lainnya`: tagihan non-bulanan, denda, dan tagihan lain, urut tanggal terbit.
        - Sel/item: `tagihan` (boleh kosong), `nama`, `nominal` (sebelum potongan), `potongan` (baris potongan +
          nota kredit yang sudah mengurangi tagihan), `bayar`, `sisa`, `tanggal_lunas`, `jatuh_tempo`, `cicilan`
          (daftar `jatuh_tempo`/`nominal`/`sisa` bila dicicil), `status` (`lunas`/`sebagian`/`belum`, atau tanpa
          tagihan: `libur` untuk bulan tidak ditagih periode komponen, selain itu `belum_terbit`).
        - `total_tagihan` (nominal − potongan), `total_bayar`, `sisa`, `saldo_kredit`, serta `siswa`,
          `tahun_ajaran`, `mata_uang`.
        """
        self.ensure_one()
        siswa = self.sudo()
        ta = tahun_ajaran.sudo()
        Move = self.env['account.move'].sudo()
        mata_uang = siswa.company_id.currency_id or self.env.company.currency_id
        awal = ta.tanggal_mulai.replace(day=1)
        bulan = [awal + relativedelta(months=i) for i in range(12)]

        def milik_ta(tagihan):
            ta_tagihan = tagihan.nti_edu_tahun_ajaran_id or tagihan.nti_edu_tagihan_asal_id.nti_edu_tahun_ajaran_id
            if ta_tagihan:
                return ta_tagihan == ta
            tanggal = tagihan.nti_edu_periode or tagihan.invoice_date
            return bool(tanggal) and ta.tanggal_mulai <= tanggal <= ta.tanggal_selesai

        semua = Move.search([
            ('move_type', '=', 'out_invoice'), ('nti_edu_is_tagihan', '=', True),
            ('nti_edu_siswa_id', '=', siswa.id), ('state', '=', 'posted'),
        ], order='invoice_date, id').filtered(milik_ta)
        nota = Move.search([
            ('move_type', '=', 'out_refund'), ('state', '=', 'posted'), ('reversed_entry_id', 'in', semua.ids)])

        bulanan_per_komponen = {}
        lainnya = []
        for tagihan in semua:
            item = self._nti_edu_rincian_kartu(tagihan, nota.filtered(lambda n: n.reversed_entry_id == tagihan))
            komponen = tagihan.nti_edu_komponen_id
            jenis = komponen.periode_jenis_id
            if komponen.jenis == 'biaya' and jenis.dasar == 'bulan' and jenis.jumlah_bulan == 1 \
                    and tagihan.nti_edu_periode in bulan and not tagihan.nti_edu_tagihan_asal_id \
                    and not tagihan.nti_edu_sumber:
                bulanan_per_komponen.setdefault(komponen, {})[tagihan.nti_edu_periode] = item
            else:
                lainnya.append(item)

        bulanan = []
        for komponen in sorted(bulanan_per_komponen, key=lambda k: (k.sequence, k.name or '', k.id)):
            libur = set(komponen.periode_jenis_id.bulan_libur_ids.mapped('nomor'))
            per_bulan = bulanan_per_komponen[komponen]
            sel = []
            for awal_bulan in bulan:
                item = per_bulan.get(awal_bulan)
                if not item:
                    item = {
                        'tagihan': Move.browse(), 'nama': komponen.name, 'nominal': 0.0, 'potongan': 0.0,
                        'bayar': 0.0, 'sisa': 0.0, 'tanggal_lunas': False, 'jatuh_tempo': False, 'cicilan': [],
                        'status': 'libur' if awal_bulan.month in libur else 'belum_terbit',
                    }
                sel.append(dict(item, bulan=awal_bulan,
                                nama_bulan=format_date(self.env, awal_bulan, date_format='MMMM y')))
            bulanan.append({'komponen': komponen, 'sel': sel})

        terbit = [s for baris in bulanan for s in baris['sel'] if s['tagihan']] + lainnya
        return {
            'siswa': siswa,
            'tahun_ajaran': ta,
            'mata_uang': mata_uang,
            'bulan': bulan,
            'bulanan': bulanan,
            'lainnya': lainnya,
            'total_tagihan': mata_uang.round(sum(i['nominal'] - i['potongan'] for i in terbit)),
            'total_bayar': mata_uang.round(sum(i['bayar'] for i in terbit)),
            'sisa': mata_uang.round(sum(i['sisa'] for i in terbit)),
            'saldo_kredit': siswa.nti_edu_saldo_kredit,
        }

    def _nti_edu_rincian_kartu(self, tagihan, nota):
        """Rincian satu tagihan (sudo) untuk Kartu SPP; `nota` = nota kredit terbit atas tagihan itu."""
        mata_uang = tagihan.currency_id
        baris = tagihan.invoice_line_ids.filtered(lambda b: b.display_type == 'product')
        nominal = sum(b.price_subtotal for b in baris if b.price_subtotal > 0)
        potongan = -sum(b.price_subtotal for b in baris if b.price_subtotal < 0)
        # Nota kredit (potongan yang diterapkan belakangan, koreksi) hanya sebesar yang sudah mengurangi tagihan.
        potongan += sum(n.amount_total - n.amount_residual for n in nota)
        sisa = tagihan.amount_residual
        bayar = mata_uang.round(nominal - potongan - sisa)
        if mata_uang.is_zero(sisa):
            status = 'lunas'
        elif mata_uang.compare_amounts(bayar, 0.0) > 0:
            status = 'sebagian'
        else:
            status = 'belum'
        piutang = tagihan._nti_edu_piutang()
        tanggal_lunas = False
        if status == 'lunas':
            tanggal_lunas = max(piutang.matched_credit_ids.mapped('max_date'), default=False) or tagihan.invoice_date
        cicilan = []
        if len(piutang) > 1:
            cicilan = [{'jatuh_tempo': b.date_maturity, 'nominal': b.amount_currency, 'sisa': b.amount_residual_currency}
                       for b in piutang]
        nama = (baris.filtered(lambda b: b.price_subtotal > 0)[:1].name or tagihan.nti_edu_komponen_id.name or '')
        if tagihan.nti_edu_periode and tagihan.nti_edu_komponen_id.periode_jenis_id.dasar != 'sekali' \
                and not tagihan.nti_edu_saldo_awal:
            nama = '%s %s' % (nama, format_date(self.env, tagihan.nti_edu_periode, date_format='MMMM y'))
        if tagihan.nti_edu_tagihan_asal_id:
            nama = _('%(denda)s atas %(asal)s', denda=nama, asal=tagihan.nti_edu_tagihan_asal_id.name)
        return {
            'tagihan': tagihan,
            'nama': nama,
            'tanggal': tagihan.invoice_date,
            'jatuh_tempo': tagihan.invoice_date_due,
            'nominal': nominal,
            'potongan': mata_uang.round(potongan),
            'bayar': bayar,
            'sisa': sisa,
            'status': status,
            'tanggal_lunas': tanggal_lunas,
            'cicilan': cicilan,
        }
