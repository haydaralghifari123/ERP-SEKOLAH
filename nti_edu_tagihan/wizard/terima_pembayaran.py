# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

GRUP_BENDAHARA = 'nti_edu_tagihan.group_tagihan_bendahara'


class BayarWizard(models.TransientModel):
    """Terima Pembayaran langsung (tunai/transfer yang diterima bendahara, spec §4.6): alokasi ke tagihan terpilih
    mulai jatuh tempo paling lama, kelebihan menjadi saldo kredit siswa, lalu cetak kuitansi."""
    _name = 'nti_edu.tagihan.bayar.wizard'
    _description = 'Wizard Terima Pembayaran'

    siswa_id = fields.Many2one(
        'res.partner', string='Siswa', required=True, domain="[('nti_edu_is_siswa', '=', True)]")
    company_id = fields.Many2one('res.company', string='Unit Sekolah', compute='_compute_company_id')
    currency_id = fields.Many2one('res.currency', string='Mata Uang', compute='_compute_company_id')
    tagihan_ids = fields.Many2many(
        'account.move', string='Tagihan', compute='_compute_tagihan_ids', store=True, readonly=False,
        precompute=True, domain="[('nti_edu_siswa_id', '=', siswa_id), ('move_type', '=', 'out_invoice'), "
               "('nti_edu_is_tagihan', '=', True), ('state', '=', 'posted'), ('amount_residual', '>', 0)]",
        help='Bawaan: semua tagihan terbuka siswa. Pembayaran dialokasikan mulai jatuh tempo paling lama.')
    total_sisa = fields.Monetary(string='Total Sisa', compute='_compute_total_sisa')
    nominal = fields.Monetary(
        string='Nominal Diterima', compute='_compute_nominal', store=True, readonly=False, precompute=True,
        required=True)
    kelebihan = fields.Monetary(
        string='Kelebihan', compute='_compute_kelebihan',
        help='Nominal di atas total sisa menjadi saldo kredit siswa yang dapat diterapkan ke tagihan berikutnya.')
    rekening_boleh_ids = fields.Many2many('nti_edu.tagihan.rekening', compute='_compute_rekening_boleh_ids')
    rekening_id = fields.Many2one(
        'nti_edu.tagihan.rekening', string='Rekening / Kas', compute='_compute_rekening_id', store=True,
        precompute=True, readonly=False, required=True, domain="[('id', 'in', rekening_boleh_ids)]")
    tanggal = fields.Date(string='Tanggal Bayar', required=True, default=fields.Date.context_today)
    memo = fields.Char(string='Keterangan', help='Kosong = nomor tagihan / referensi bawaan Odoo.')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        konteks = self.env.context
        model, ids = konteks.get('active_model'), konteks.get('active_ids') or []
        if model == 'account.move' and ids and not res.get('siswa_id'):
            dipilih = self.env['account.move'].browse(ids)
            siswa = dipilih.nti_edu_siswa_id
            if len(siswa) > 1:
                raise UserError(_('Pilih tagihan dari satu siswa saja.'))
            if siswa:
                res['siswa_id'] = siswa.id
                terbuka = dipilih.filtered(lambda m: m._nti_edu_terbuka())
                if terbuka and 'tagihan_ids' in fields_list:
                    res['tagihan_ids'] = [(6, 0, terbuka.ids)]
        elif model == 'res.partner' and konteks.get('active_id') and not res.get('siswa_id'):
            partner = self.env['res.partner'].browse(konteks['active_id'])
            if partner.nti_edu_is_siswa:
                res['siswa_id'] = partner.id
        return res

    @api.depends('siswa_id')
    def _compute_company_id(self):
        for rec in self:
            company = rec.siswa_id.sudo().company_id
            rec.company_id = company
            rec.currency_id = company.currency_id or self.env.company.currency_id

    @api.depends('siswa_id')
    def _compute_tagihan_ids(self):
        Move = self.env['account.move']
        for rec in self:
            # Pilihan yang sudah ada (mis. dari daftar tagihan) dipertahankan selama siswanya sama.
            if rec.tagihan_ids and rec.tagihan_ids._origin.nti_edu_siswa_id == rec.siswa_id._origin:
                continue
            if not rec.siswa_id:
                rec.tagihan_ids = Move
                continue
            rec.tagihan_ids = Move.search([
                ('nti_edu_siswa_id', '=', rec.siswa_id.id), ('move_type', '=', 'out_invoice'),
                ('nti_edu_is_tagihan', '=', True), ('state', '=', 'posted'), ('amount_residual', '>', 0),
            ], order='invoice_date_due, id')

    @api.depends('tagihan_ids')
    def _compute_total_sisa(self):
        for rec in self:
            rec.total_sisa = sum(rec.tagihan_ids.mapped('amount_residual'))

    @api.depends('tagihan_ids')
    def _compute_nominal(self):
        for rec in self:
            rec.nominal = sum(rec.tagihan_ids.mapped('amount_residual'))

    @api.depends('nominal', 'total_sisa')
    def _compute_kelebihan(self):
        for rec in self:
            rec.kelebihan = max(rec.nominal - rec.total_sisa, 0.0)

    @api.depends('siswa_id')
    def _compute_rekening_boleh_ids(self):
        Rekening = self.env['nti_edu.tagihan.rekening']
        for rec in self:
            rec.rekening_boleh_ids = Rekening._untuk_unit(rec.company_id) if rec.company_id else Rekening

    @api.depends('siswa_id')
    def _compute_rekening_id(self):
        for rec in self:
            boleh = rec.rekening_boleh_ids._origin
            if rec.rekening_id._origin not in boleh:
                rec.rekening_id = boleh[:1]

    def action_bayar(self):
        self.ensure_one()
        siswa = self.siswa_id.sudo()
        self.env['nti_edu.tagihan.akses']._nti_edu_cek_hak(GRUP_BENDAHARA, siswa.company_id)
        if not self.tagihan_ids:
            raise UserError(_('Siswa %s tidak punya tagihan terbuka yang dipilih.', siswa.name))
        lain = self.tagihan_ids.sudo().filtered(lambda m: m.nti_edu_siswa_id != siswa)
        if lain:
            raise UserError(_('Tagihan %(tagihan)s bukan milik siswa %(siswa)s.',
                              tagihan=', '.join(lain.mapped('name')), siswa=siswa.name))
        payments = self.env['nti_edu.tagihan.mesin']._bayar(
            self.tagihan_ids, self.nominal, self.rekening_id, self.tanggal, self.memo, siswa_kelebihan=siswa)
        # Kuitansi = laporan tanda terima pembayaran Odoo (judul "Kuitansi Pembayaran", kop unit payment).
        return self.env.ref('account.action_report_payment_receipt').sudo().report_action(payments, config=False)
