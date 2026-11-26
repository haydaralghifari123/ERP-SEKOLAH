# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'


class BuatTagihanWizard(models.TransientModel):
    """Wizard Buat Tagihan (spec §4.3): bendahara memilih komponen, periode, dan rombel, melihat pratinjau, lalu
    menerbitkan tagihan lewat mesin yang sama dengan jadwal harian."""
    _name = 'nti_edu.tagihan.buat.wizard'
    _description = 'Wizard Buat Tagihan'

    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', required=True, default=lambda self: self.env.company,
        domain="[('id', 'in', allowed_company_ids), ('nti_edu_jenis', '=', 'unit')]")
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    komponen_id = fields.Many2one(
        'nti_edu.tagihan.komponen', string='Komponen Biaya', required=True,
        domain="[('jenis', '=', 'biaya'), '|', ('company_id', '=', False), ('company_id', 'parent_of', company_id)]")
    periode_dasar = fields.Selection(related='komponen_id.periode_jenis_id.dasar', string='Dasar Periode')
    tahun_ajaran_id = fields.Many2one(
        'nti_edu.tahun.ajaran', string='Tahun Ajaran', required=True,
        default=lambda self: self.env['nti_edu.tahun.ajaran']._get_aktif())
    periode = fields.Date(
        string='Periode', compute='_compute_periode', store=True, readonly=False,
        help='Tanggal awal periode tagihan (mis. 1 Agustus untuk SPP Agustus); kosong untuk komponen sekali.')
    daftar_periode = fields.Char(string='Periode Tersedia', compute='_compute_daftar_periode')
    rombel_ids = fields.Many2many(
        'nti_edu.rombel', string='Rombel',
        domain="[('company_id', '=', company_id), ('tahun_ajaran_id', '=', tahun_ajaran_id)]",
        help='Kosong = semua rombel unit.')
    jumlah_siswa = fields.Integer(string='Jumlah Siswa Ditagih', compute='_compute_pratinjau')
    total = fields.Monetary(string='Total Tagihan', currency_field='currency_id', compute='_compute_pratinjau')
    daftar_lewati = fields.Text(string='Siswa Dilewati', compute='_compute_pratinjau')

    # --- periode -----------------------------------------------------------------------------

    def _daftar_info(self):
        self.ensure_one()
        if not (self.komponen_id and self.tahun_ajaran_id):
            return []
        return self.env['nti_edu.tagihan.mesin']._periode_dalam_tahun(self.komponen_id, self.tahun_ajaran_id)

    def _info_terpilih(self):
        """Periode dari `_periode_dalam_tahun` yang cocok dengan pilihan wizard; `None` bila tidak ada."""
        self.ensure_one()
        for info in self._daftar_info():
            if (info['periode'] or False) == (self.periode or False):
                return info
        return None

    @api.depends('komponen_id', 'tahun_ajaran_id')
    def _compute_periode(self):
        hari_ini = fields.Date.context_today(self)
        for rec in self:
            daftar = [i for i in rec._daftar_info() if i['periode']]
            if not daftar:
                rec.periode = False
                continue
            sudah_terbit = [i for i in daftar if i['terbit'] <= hari_ini]
            rec.periode = (sudah_terbit[-1] if sudah_terbit else daftar[0])['periode']

    @api.depends('komponen_id', 'tahun_ajaran_id')
    def _compute_daftar_periode(self):
        for rec in self:
            daftar = [i['periode'] for i in rec._daftar_info() if i['periode']]
            rec.daftar_periode = ', '.join(format_date(self.env, p) for p in daftar) or False

    @api.constrains('komponen_id', 'tahun_ajaran_id', 'periode')
    def _cek_periode(self):
        for rec in self:
            rec._pastikan_periode()

    def _pastikan_periode(self):
        info = self._info_terpilih()
        if info is not None:
            return info
        if self.komponen_id.periode_jenis_id.dasar == 'sekali':
            raise ValidationError(_(
                'Komponen "%s" ditagih sekali sehingga tidak memakai periode; kosongkan Periode.',
                self.komponen_id.name))
        raise ValidationError(_(
            'Periode %(periode)s bukan awal periode tagihan "%(komponen)s" pada tahun ajaran %(ta)s. '
            'Pilih salah satu: %(daftar)s.',
            periode=format_date(self.env, self.periode) if self.periode else _('(kosong)'),
            komponen=self.komponen_id.name, ta=self.tahun_ajaran_id.name,
            daftar=self.daftar_periode or _('(tidak ada)')))

    # --- pratinjau ---------------------------------------------------------------------------

    def _boleh_lihat(self):
        """Pratinjau memuat nama siswa: hanya untuk bendahara unit tersebut."""
        self.ensure_one()
        if self.env.su:
            return True
        user = self.env.user
        return user.has_group(GRUP_BENDAHARA) and self.company_id._origin in user.company_ids

    @api.depends('company_id', 'komponen_id', 'tahun_ajaran_id', 'periode', 'rombel_ids')
    def _compute_pratinjau(self):
        Mesin = self.env['nti_edu.tagihan.mesin']
        for rec in self:
            rec.jumlah_siswa = 0
            rec.total = 0.0
            rec.daftar_lewati = False
            if not rec.company_id or not rec._boleh_lihat():
                continue
            info = rec._info_terpilih()
            if info is None:
                continue
            rencana = Mesin._rencana(
                rec.company_id._origin, rec.komponen_id._origin, info, rombel=rec.rombel_ids._origin or None)
            rec.jumlah_siswa = len(rencana['buat'])
            rec.total = sum(
                item['nominal'] - sum(jumlah for _jenis, jumlah in item['potongan']) for item in rencana['buat'])
            rec.daftar_lewati = rec._format_lewati(rencana['lewati'])

    @api.model
    def _format_lewati(self, lewati):
        return '\n'.join('%s: %s' % (siswa.sudo().display_name, alasan) for siswa, alasan in lewati) or False

    # --- terbitkan ---------------------------------------------------------------------------

    def action_terbitkan(self):
        self.ensure_one()
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, self.company_id)
        info = self._pastikan_periode()
        mulai = self.company_id.sudo().nti_edu_tagihan_mulai
        if info['periode'] and mulai and info['periode'] < mulai:
            raise UserError(_(
                'Periode %(periode)s dimulai sebelum Tagihan Mulai unit %(unit)s (%(mulai)s); tagihan periode itu '
                'tidak diterbitkan. Gunakan Tunggakan Awal untuk tunggakan lama.',
                periode=format_date(self.env, info['periode']), unit=self.company_id.name,
                mulai=format_date(self.env, mulai)))
        hasil = self.env['nti_edu.tagihan.mesin']._terbitkan(
            self.company_id, self.komponen_id, info, rombel=self.rombel_ids or None)
        jumlah_terbit, jumlah_lewati = len(hasil['buat']), len(hasil['lewati'])
        pesan = _('%(terbit)s tagihan terbit, %(lewati)s siswa dilewati.',
                  terbit=jumlah_terbit, lewati=jumlah_lewati)
        if hasil['lewati']:
            pesan = '%s\n%s' % (pesan, self._format_lewati(hasil['lewati']))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Buat Tagihan'),
                'message': pesan,
                'type': 'warning' if jumlah_lewati else 'success',
                'sticky': bool(jumlah_lewati),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
