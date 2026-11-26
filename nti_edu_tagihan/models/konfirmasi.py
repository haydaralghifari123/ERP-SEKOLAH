# -*- coding: utf-8 -*-
import base64
import binascii
import contextvars
import os
from contextlib import contextmanager

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'

# Penanda bahwa penulisan berasal dari aksi modul (Terima/Tolak). Sengaja bukan kunci context Odoo: context bisa
# dikirim bebas lewat RPC, sedangkan ContextVar hanya bisa dipasang kode server.
_AKSI_KONFIRMASI = contextvars.ContextVar('nti_edu_aksi_konfirmasi', default=False)

# Field yang boleh diubah langsung (oleh Bendahara unit) selama konfirmasi masih menunggu.
FIELD_BOLEH_UBAH = {'nominal_diterima'}

# Field yang boleh diisi pemanggil `_buat_dari_portal`; sisanya diisi server.
FIELD_PORTAL = {
    'tanggal_transfer', 'nominal', 'rekening_id', 'nama_rekening_pengirim', 'bukti', 'bukti_nama', 'catatan',
}

# Ekstensi bukti yang diterima dan tanda awal (magic bytes) isi berkasnya.
TANDA_BERKAS = {
    '.jpg': b'\xff\xd8',
    '.jpeg': b'\xff\xd8',
    '.png': b'\x89PNG',
    '.pdf': b'%PDF',
}
EKSTENSI_GAMBAR = {'.jpg', '.jpeg', '.png'}


@contextmanager
def _aksi_konfirmasi():
    token = _AKSI_KONFIRMASI.set(True)
    try:
        yield
    finally:
        _AKSI_KONFIRMASI.reset(token)


def _ekstensi(nama):
    return os.path.splitext((nama or '').strip().lower())[1]


class TagihanKonfirmasi(models.Model):
    """Konfirmasi transfer yang dikirim wali/siswa dari portal dan diverifikasi Bendahara unit (spec §4.6).

    Satu konfirmasi memuat satu atau beberapa tagihan dari satu unit. Dibuat hanya lewat `_buat_dari_portal`
    (pemeriksaan di server); status hanya berubah lewat tombol Terima/Tolak.
    """
    _name = 'nti_edu.tagihan.konfirmasi'
    _inherit = ['mail.thread']
    _description = 'Konfirmasi Transfer'
    _order = 'id desc'

    name = fields.Char(string='Nomor', required=True, readonly=True, copy=False, default='/')
    pengirim_id = fields.Many2one(
        'res.partner', string='Pengirim', required=True, readonly=True, index=True, ondelete='restrict')
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', required=True, readonly=True, index=True, ondelete='restrict')
    currency_id = fields.Many2one(related='company_id.currency_id', string='Mata Uang')
    tagihan_ids = fields.Many2many(
        'account.move', 'nti_edu_tagihan_konfirmasi_move_rel', 'konfirmasi_id', 'move_id',
        string='Tagihan', readonly=True)
    siswa_ids = fields.Many2many(
        'res.partner', 'nti_edu_tagihan_konfirmasi_siswa_rel', 'konfirmasi_id', 'siswa_id',
        string='Siswa', compute='_compute_siswa_ids', store=True)
    tanggal_transfer = fields.Date(string='Tanggal Transfer', required=True, readonly=True)
    nominal = fields.Monetary(string='Nominal Dilaporkan', required=True, readonly=True)
    nominal_diterima = fields.Monetary(
        string='Nominal Diterima', tracking=True,
        help='Diisi Bendahara bila uang yang masuk berbeda dari laporan; kosong = nominal dilaporkan.')
    rekening_id = fields.Many2one(
        'nti_edu.tagihan.rekening', string='Rekening Tujuan', required=True, readonly=True, ondelete='restrict')
    nama_rekening_pengirim = fields.Char(string='Nama Pemilik Rekening Pengirim', required=True, readonly=True)
    bukti = fields.Binary(string='Bukti Transfer', attachment=True, required=True, readonly=True)
    bukti_nama = fields.Char(string='Nama Berkas Bukti', required=True, readonly=True)
    bukti_is_gambar = fields.Boolean(string='Bukti Berupa Gambar', compute='_compute_bukti_is_gambar')
    catatan = fields.Text(string='Catatan Pengirim', readonly=True)
    state = fields.Selection([
        ('menunggu', 'Menunggu Verifikasi'),
        ('diterima', 'Diterima'),
        ('ditolak', 'Ditolak'),
    ], string='Status', required=True, default='menunggu', readonly=True, index=True, tracking=True)
    alasan_tolak_id = fields.Many2one(
        'nti_edu.tagihan.alasan.tolak', string='Alasan Penolakan', readonly=True, ondelete='restrict')
    catatan_tolak = fields.Text(string='Catatan Penolakan', readonly=True)
    payment_ids = fields.Many2many(
        'account.payment', 'nti_edu_tagihan_konfirmasi_payment_rel', 'konfirmasi_id', 'payment_id',
        string='Pembayaran', readonly=True, copy=False)
    diverifikasi_oleh_id = fields.Many2one('res.users', string='Diverifikasi Oleh', readonly=True, copy=False)
    tanggal_verifikasi = fields.Datetime(string='Tanggal Verifikasi', readonly=True, copy=False)

    @api.depends('tagihan_ids.nti_edu_siswa_id')
    def _compute_siswa_ids(self):
        for rec in self:
            rec.siswa_ids = rec.sudo().tagihan_ids.nti_edu_siswa_id.sorted(lambda s: (s.name or '', s.id))

    @api.depends('bukti_nama')
    def _compute_bukti_is_gambar(self):
        for rec in self:
            rec.bukti_is_gambar = _ekstensi(rec.bukti_nama) in EKSTENSI_GAMBAR

    @api.constrains('nominal', 'nominal_diterima')
    def _cek_nominal(self):
        for rec in self:
            if rec.currency_id.compare_amounts(rec.nominal, 0.0) <= 0:
                raise ValidationError(_('Nominal transfer harus lebih dari nol.'))
            if rec.currency_id.compare_amounts(rec.nominal_diterima, 0.0) < 0:
                raise ValidationError(_('Nominal diterima tidak boleh negatif.'))

    @api.model_create_multi
    def create(self, vals_list):
        Sequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = Sequence.next_by_code('nti_edu.tagihan.konfirmasi') or '/'
        return super(TagihanKonfirmasi, self.with_context(mail_create_nosubscribe=True)).create(vals_list)

    def write(self, vals):
        # Penjaga tulis (spec §4.6, §4.11): di luar aksi Terima/Tolak hanya nominal diterima yang boleh diubah,
        # dan hanya selama menunggu. Field teknis chatter (message_*) tetap boleh ditulis mail.thread.
        if not _AKSI_KONFIRMASI.get():
            diubah = {f for f in vals if not f.startswith('message_')}
            if diubah:
                if self.sudo().filtered(lambda k: k.state != 'menunggu'):
                    raise UserError(_('Konfirmasi transfer yang sudah diverifikasi tidak dapat diubah.'))
                if diubah - FIELD_BOLEH_UBAH:
                    raise UserError(_(
                        'Konfirmasi transfer hanya dapat diubah lewat tombol Terima atau Tolak; yang boleh diubah '
                        'langsung hanya nominal diterima.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise UserError(_('Konfirmasi transfer tidak dapat dihapus; tolak bila tidak sah.'))
        return super().unlink()

    # --- pengiriman dari portal ----------------------------------------------------------------

    @api.model
    def _buat_dari_portal(self, user, tagihan_ids, vals):
        """Buat konfirmasi transfer atas nama `user` (portal atau internal) untuk tagihan `tagihan_ids`.

        Semua pemeriksaan dilakukan di server: tagihan sekolah terbit yang belum lunas milik siswa yang terhubung
        dengan `user` (termasuk anak nonaktif), dari satu unit; rekening berlaku untuk unit itu; bukti wajib
        (jpg/jpeg/png/pdf, isi cocok jenisnya, ukuran ≤ batas unit). `vals` hanya berisi FIELD_PORTAL dengan
        `bukti` ber-base64. Ditulis sebagai superuser; mengembalikan konfirmasi (sudo). Selain itu `UserError`.
        """
        user = user.sudo()
        user.ensure_one()
        tidak_dikenal = set(vals) - FIELD_PORTAL
        if tidak_dikenal:
            raise ValueError('Field konfirmasi tidak dikenal: %s' % ', '.join(sorted(tidak_dikenal)))
        if isinstance(tagihan_ids, models.BaseModel):
            tagihan_ids = tagihan_ids.ids
        tagihan = self.env['account.move'].sudo().browse(tagihan_ids or []).exists()
        if not tagihan:
            raise UserError(_('Pilih minimal satu tagihan yang dikonfirmasi.'))
        # Pesan sengaja umum: nama tagihan siswa lain tidak boleh bocor ke pengirim.
        siswa_boleh = user._nti_edu_siswa_portal(termasuk_nonaktif=True)
        if len(tagihan) != len(set(tagihan_ids)) or tagihan.filtered(
                lambda m: m.nti_edu_siswa_id not in siswa_boleh or not m.nti_edu_is_tagihan):
            raise UserError(_('Tagihan yang dipilih tidak ditemukan atau bukan tagihan anak Anda.'))
        if tagihan.filtered(lambda m: not m._nti_edu_terbuka()):
            raise UserError(_('Sebagian tagihan yang dipilih sudah lunas atau tidak lagi berlaku.'))
        company = tagihan.company_id
        if len(company) != 1:
            raise UserError(_(
                'Satu konfirmasi transfer hanya boleh memuat tagihan dari satu unit sekolah; kirim konfirmasi '
                'terpisah untuk tiap unit.'))

        mata_uang = company.currency_id
        nominal = vals.get('nominal') or 0.0
        if mata_uang.compare_amounts(nominal, 0.0) <= 0:
            raise UserError(_('Nominal transfer harus lebih dari nol.'))
        if not vals.get('tanggal_transfer'):
            raise UserError(_('Tanggal transfer wajib diisi.'))
        if not (vals.get('nama_rekening_pengirim') or '').strip():
            raise UserError(_('Nama pemilik rekening pengirim wajib diisi.'))
        Rekening = self.env['nti_edu.tagihan.rekening'].sudo()
        rekening = Rekening.browse(vals.get('rekening_id') or []).exists()
        if len(rekening) != 1 or rekening not in Rekening._untuk_unit(company):
            raise UserError(_('Rekening tujuan tidak berlaku untuk unit %s.', company.name))
        self._cek_bukti(vals.get('bukti'), vals.get('bukti_nama'), company)

        nilai = dict(vals, **{
            'pengirim_id': user.partner_id.id,
            'company_id': company.id,
            'tagihan_ids': [(6, 0, tagihan.ids)],
            'rekening_id': rekening.id,
            'nama_rekening_pengirim': vals['nama_rekening_pengirim'].strip(),
            'bukti_nama': os.path.basename(vals['bukti_nama'].strip().replace('\\', '/')),
        })
        return self.sudo().create(nilai)

    @api.model
    def _cek_bukti(self, bukti, nama, company):
        """`UserError` bila bukti kosong, jenisnya bukan jpg/jpeg/png/pdf, isinya tidak cocok dengan jenisnya, atau
        ukurannya melebihi `nti_edu_bukti_ukuran_maks_mb` unit."""
        if not bukti or not (nama or '').strip():
            raise UserError(_('Bukti transfer wajib diunggah.'))
        tanda = TANDA_BERKAS.get(_ekstensi(nama))
        if not tanda:
            raise UserError(_('Bukti transfer harus berkas JPG, PNG, atau PDF.'))
        try:
            isi = base64.b64decode(bukti, validate=True)
        except (binascii.Error, ValueError, TypeError):
            raise UserError(_('Berkas bukti transfer tidak dapat dibaca.')) from None
        maks = company.sudo().nti_edu_bukti_ukuran_maks_mb
        if len(isi) > maks * 1024 * 1024:
            raise UserError(_('Ukuran bukti transfer melebihi batas %s MB.', maks))
        if not isi.startswith(tanda):
            raise UserError(_('Isi berkas bukti transfer tidak sesuai dengan jenisnya (JPG, PNG, atau PDF).'))

    # --- verifikasi ----------------------------------------------------------------------------

    def _cek_verifikasi(self):
        """Hak Bendahara unit konfirmasi + record rule, lalu status harus menunggu."""
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, self.sudo().company_id)
        if not self.env.su:
            self.check_access('write')
        if self.sudo().filtered(lambda k: k.state != 'menunggu'):
            raise UserError(_('Konfirmasi transfer ini sudah diverifikasi.'))

    def action_terima(self):
        """Terima transfer: catat pembayaran `nominal_diterima` (atau nominal laporan) ke tagihan konfirmasi yang
        masih terbuka, jatuh tempo terlama lebih dahulu. Kelebihan — atau seluruhnya bila tidak ada tagihan yang
        masih terbuka (lunas tunai atau dibatalkan) — menjadi saldo kredit siswa pertama konfirmasi menurut nama.
        Email "diterima" ke pengirim."""
        self._cek_verifikasi()
        for konf in self.sudo():
            jumlah = konf.nominal_diterima or konf.nominal
            payments = konf.with_env(self.env)._catat_pembayaran(jumlah)
            with _aksi_konfirmasi():
                konf.write({
                    'state': 'diterima',
                    'nominal_diterima': jumlah,
                    'payment_ids': [(6, 0, payments.ids)],
                    'diverifikasi_oleh_id': self.env.uid,
                    'tanggal_verifikasi': fields.Datetime.now(),
                })
            konf._catat(_('Transfer diterima sebesar %(nominal)s; pembayaran %(payment)s.',
                          nominal=format_amount(self.env, jumlah, konf.currency_id),
                          payment=', '.join(payments.sudo().mapped('name'))))
            konf._kirim_email('nti_edu_tagihan.mail_template_konfirmasi_diterima')
        return True

    def _catat_pembayaran(self, jumlah):
        """Payment `jumlah` untuk konfirmasi ini, dicatat atas nama pemanggil (`self` dalam env pemanggil, bukan
        sudo, agar mesin memeriksa hak Bendahara unit).

        Bagian sebesar total sisa tagihan terbuka dibayarkan lewat `_bayar` (satu payment per siswa); kelebihan
        menjadi kredit siswa pertama konfirmasi menurut nama. Bila siswa itu masih punya tagihan terbuka di sini,
        kelebihan ikut payment-nya (`siswa_kelebihan`); bila tidak (tagihannya lunas tunai atau dibatalkan),
        dicatat sebagai payment kredit tersendiri lewat `_bayar_sebagai_kredit`."""
        self.ensure_one()
        konf = self.sudo()
        Mesin = self.env['nti_edu.tagihan.mesin']
        mata_uang = konf.currency_id
        siswa_kredit = konf.siswa_ids.sorted(lambda s: (s.name or '', s.id))[:1]
        terbuka = konf.tagihan_ids.filtered(lambda m: m._nti_edu_terbuka())
        rekening, tanggal, memo = konf.rekening_id, konf.tanggal_transfer, konf.name
        if terbuka and siswa_kredit in terbuka.nti_edu_siswa_id:
            return Mesin._bayar(terbuka, jumlah, rekening, tanggal, memo, siswa_kelebihan=siswa_kredit)
        alokasi = min(jumlah, sum(terbuka.mapped('amount_residual')))
        kelebihan = mata_uang.round(jumlah - alokasi)
        payments = self.env['account.payment']
        if mata_uang.compare_amounts(alokasi, 0.0) > 0:
            payments |= Mesin._bayar(terbuka, alokasi, rekening, tanggal, memo)
        if mata_uang.compare_amounts(kelebihan, 0.0) > 0:
            payments |= Mesin._bayar_sebagai_kredit(siswa_kredit, konf.company_id, kelebihan, rekening, tanggal, memo)
        return payments

    def action_tolak(self):
        """Buka wizard penolakan (alasan wajib)."""
        self.ensure_one()
        self._cek_verifikasi()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tolak Konfirmasi Transfer'),
            'res_model': 'nti_edu.tagihan.tolak.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_konfirmasi_id': self.id},
        }

    def _tolak(self, alasan, catatan=False):
        """Tolak konfirmasi dengan `alasan` (master alasan penolakan) dan `catatan` (wajib bila alasan
        mewajibkannya); email "ditolak" ke pengirim."""
        self._cek_verifikasi()
        alasan = alasan.sudo()
        catatan = (catatan or '').strip()
        if not alasan:
            raise UserError(_('Alasan penolakan wajib dipilih.'))
        if alasan.perlu_catatan and not catatan:
            raise UserError(_('Alasan "%s" mewajibkan catatan penolakan.', alasan.name))
        for konf in self.sudo():
            if not alasan.filtered_domain(alasan._check_company_domain(konf.company_id)):
                raise UserError(_('Alasan "%(alasan)s" tidak berlaku untuk unit %(unit)s.',
                                  alasan=alasan.name, unit=konf.company_id.name))
            with _aksi_konfirmasi():
                konf.write({
                    'state': 'ditolak',
                    'alasan_tolak_id': alasan.id,
                    'catatan_tolak': catatan or False,
                    'diverifikasi_oleh_id': self.env.uid,
                    'tanggal_verifikasi': fields.Datetime.now(),
                })
            konf._catat(_('Konfirmasi ditolak. Alasan: %(alasan)s%(catatan)s',
                          alasan=alasan.name, catatan=(' — %s' % catatan) if catatan else ''))
            konf._kirim_email('nti_edu_tagihan.mail_template_konfirmasi_ditolak')
        return True

    # --- chatter & email -----------------------------------------------------------------------

    def _catat(self, pesan):
        """Catatan internal di chatter atas nama pemanggil."""
        self.ensure_one()
        self.sudo().message_post(
            body=pesan, subtype_xmlid='mail.mt_note', author_id=self.env.user.partner_id.id)

    def _kirim_email(self, template_xmlid):
        """Antrekan email templat ke pengirim (spec §4.6); bila pengirim tidak punya email, catat di chatter."""
        self.ensure_one()
        konf = self.sudo()
        if not konf.pengirim_id.email:
            konf._catat(_('Email ke pengirim tidak dikirim: %s tidak memiliki alamat email.',
                          konf.pengirim_id.display_name))
            return
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if not template:
            konf._catat(_('Email ke pengirim tidak dikirim: templat email tidak ditemukan.'))
            return
        template.sudo().send_mail(konf.id, force_send=False)
