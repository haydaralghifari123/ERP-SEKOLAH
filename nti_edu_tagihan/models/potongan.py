# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

GRUP_ADMIN = 'nti_edu_tagihan.group_tagihan_admin'


def _cek_nilai_potongan(tipe, nilai, nama):
    if nilai < 0:
        raise ValidationError(_('Nilai potongan "%s" tidak boleh negatif.', nama))
    if tipe == 'persen' and nilai > 100:
        raise ValidationError(_('Potongan persen "%s" tidak boleh lebih dari 100.', nama))


class TagihanPotonganJenis(models.Model):
    _name = 'nti_edu.tagihan.potongan.jenis'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Jenis Potongan'

    tipe = fields.Selection([
        ('persen', 'Persen'),
        ('nominal', 'Nominal'),
    ], string='Tipe', required=True, default='persen')
    nilai_bawaan = fields.Float(string='Nilai Bawaan', help='Persen (0-100) atau nominal rupiah sesuai tipe.')
    komponen_ids = fields.Many2many(
        'nti_edu.tagihan.komponen', string='Berlaku untuk Komponen', domain="[('jenis', '=', 'biaya')]",
        help='Potongan hanya berlaku untuk komponen yang dipilih; kosong = tidak berlaku untuk komponen mana pun.')
    dapat_digabung = fields.Boolean(
        string='Dapat Digabung', default=True,
        help='Potongan yang dapat digabung dijumlahkan; yang tidak dapat digabung hanya dipakai bila lebih besar '
             'dari gabungan itu.')
    perlu_persetujuan = fields.Boolean(
        string='Perlu Persetujuan', help='Potongan siswa jenis ini baru aktif setelah disetujui Admin Keuangan.')

    @api.constrains('tipe', 'nilai_bawaan')
    def _cek_nilai(self):
        for rec in self:
            _cek_nilai_potongan(rec.tipe, rec.nilai_bawaan, rec.name)


class TagihanPotongan(models.Model):
    _name = 'nti_edu.tagihan.potongan'
    _description = 'Potongan Siswa'
    _order = 'tanggal_mulai desc, id desc'
    _inherit = ['mail.thread']

    # Field yang tidak boleh diubah bendahara setelah potongan lewat tahap draf.
    _FIELD_TERKUNCI = ('siswa_id', 'jenis_id', 'nilai', 'tanggal_mulai', 'tanggal_selesai', 'state')

    siswa_id = fields.Many2one(
        'res.partner', string='Siswa', required=True, index=True, ondelete='restrict',
        domain="[('nti_edu_is_siswa', '=', True)]", tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', related='siswa_id.company_id', store=True, index=True)
    jenis_id = fields.Many2one(
        'nti_edu.tagihan.potongan.jenis', string='Jenis Potongan', required=True, ondelete='restrict',
        tracking=True)
    tipe = fields.Selection(related='jenis_id.tipe')
    nilai = fields.Float(string='Nilai', required=True, tracking=True, help='Persen (0-100) atau nominal rupiah.')
    tanggal_mulai = fields.Date(string='Tanggal Mulai', required=True, tracking=True)
    tanggal_selesai = fields.Date(string='Tanggal Selesai', tracking=True, help='Kosong = tanpa batas akhir.')
    alasan = fields.Text(string='Alasan')
    lampiran = fields.Binary(string='Lampiran', attachment=True)
    lampiran_nama = fields.Char(string='Nama Lampiran')
    state = fields.Selection([
        ('draft', 'Draf'),
        ('menunggu', 'Menunggu Persetujuan'),
        ('aktif', 'Aktif'),
        ('berakhir', 'Berakhir'),
        ('ditolak', 'Ditolak'),
    ], string='Status', required=True, default='draft', copy=False, tracking=True)

    @api.onchange('jenis_id')
    def _onchange_jenis_id(self):
        if self.jenis_id:
            self.nilai = self.jenis_id.nilai_bawaan

    @api.constrains('siswa_id')
    def _cek_siswa(self):
        for rec in self:
            if not rec.siswa_id.nti_edu_is_siswa:
                raise ValidationError(_('"%s" bukan siswa.', rec.siswa_id.display_name))

    @api.constrains('jenis_id', 'nilai', 'tanggal_mulai', 'tanggal_selesai')
    def _cek_potongan(self):
        for rec in self:
            _cek_nilai_potongan(rec.jenis_id.tipe, rec.nilai, rec.jenis_id.name)
            if rec.tanggal_selesai and rec.tanggal_selesai < rec.tanggal_mulai:
                raise ValidationError(_('Tanggal selesai potongan tidak boleh sebelum tanggal mulai.'))

    # --- penjaga tulis -----------------------------------------------------------------------

    def _boleh_kelola(self):
        """Admin Keuangan (termasuk Admin Sistem) dan superuser bebas mengubah potongan."""
        return self.env.su or self.env.user.has_group(GRUP_ADMIN)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'nilai' not in vals and vals.get('jenis_id'):
                vals['nilai'] = self.env['nti_edu.tagihan.potongan.jenis'].browse(vals['jenis_id']).nilai_bawaan
            if vals.get('state', 'draft') != 'draft' and not self._boleh_kelola():
                raise AccessError(_('Potongan baru harus dibuat sebagai draf lalu diajukan.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self._boleh_kelola() and any(f in vals for f in self._FIELD_TERKUNCI):
            if 'state' in vals or any(rec.state != 'draft' for rec in self):
                raise AccessError(_(
                    'Potongan yang sudah diajukan tidak dapat diubah. Gunakan tombol Ajukan, Setujui, Tolak, '
                    'atau Akhiri, atau minta Admin Keuangan.'))
        return super().write(vals)

    def unlink(self):
        if not self._boleh_kelola() and any(rec.state in ('aktif', 'berakhir') for rec in self):
            raise AccessError(_('Potongan yang aktif atau sudah berakhir tidak dapat dihapus.'))
        return super().unlink()

    # --- alur --------------------------------------------------------------------------------

    def _ubah_status(self, dari, ke, pesan):
        """Ubah status lewat sudo setelah hak tulis diperiksa; penjaga tulis menutup perubahan langsung."""
        self.check_access('write')
        if any(rec.state not in dari for rec in self):
            raise ValidationError(pesan)
        self.sudo().write({'state': ke})

    def action_ajukan(self):
        self.check_access('write')
        for rec in self:
            rec._ubah_status(
                ('draft',), 'menunggu' if rec.jenis_id.perlu_persetujuan else 'aktif',
                _('Hanya potongan berstatus draf yang dapat diajukan.'))

    def _cek_admin(self):
        if not self._boleh_kelola():
            raise AccessError(_('Hanya Admin Keuangan yang dapat menyetujui atau menolak potongan.'))

    def action_setujui(self):
        self._cek_admin()
        self._ubah_status(('menunggu',), 'aktif', _('Hanya potongan yang menunggu persetujuan yang dapat disetujui.'))

    def action_tolak(self):
        self._cek_admin()
        self._ubah_status(('menunggu',), 'ditolak', _('Hanya potongan yang menunggu persetujuan yang dapat ditolak.'))

    def action_akhiri(self):
        self._ubah_status(('aktif',), 'berakhir', _('Hanya potongan aktif yang dapat diakhiri.'))

    # --- perhitungan -------------------------------------------------------------------------

    @api.model
    def _hitung(self, siswa, komponen, tanggal, nominal):
        """Potongan untuk `siswa` pada `komponen` bertanggal `tanggal` dengan `nominal` tagihan.

        Mengembalikan daftar (jenis, jumlah). Potongan yang dapat digabung dijumlahkan (himpunan A); potongan
        tidak-dapat-digabung terbesar (himpunan B) dipakai bila lebih besar dari A (seri: A). Total tidak
        melebihi `nominal`; pemangkasan dari item terakhir.
        """
        if nominal <= 0:
            return []
        siswa = siswa.sudo()
        daftar = self.sudo().search([
            ('siswa_id', '=', siswa.id), ('state', '=', 'aktif'), ('tanggal_mulai', '<=', tanggal),
            '|', ('tanggal_selesai', '=', False), ('tanggal_selesai', '>=', tanggal),
            ('jenis_id.komponen_ids', 'in', komponen.ids)], order='id')
        mata_uang = (siswa.company_id or self.env.company).currency_id
        himpunan_a, terbaik_b = [], None
        for pot in daftar:
            if pot.tipe == 'persen':
                jumlah = mata_uang.round(nominal * pot.nilai / 100.0)
            else:
                jumlah = mata_uang.round(pot.nilai)
            jumlah = min(jumlah, nominal)
            if jumlah <= 0:
                continue
            if pot.jenis_id.dapat_digabung:
                himpunan_a.append((pot.jenis_id, jumlah))
            elif terbaik_b is None or jumlah > terbaik_b[1]:
                terbaik_b = (pot.jenis_id, jumlah)
        total_a = min(sum(jumlah for _jenis, jumlah in himpunan_a), nominal)
        if terbaik_b and terbaik_b[1] > total_a:
            return [terbaik_b]
        hasil, sisa = [], nominal
        for jenis, jumlah in himpunan_a:
            jumlah = min(jumlah, sisa)
            if jumlah > 0:
                hasil.append((jenis, jumlah))
                sisa -= jumlah
        return hasil
