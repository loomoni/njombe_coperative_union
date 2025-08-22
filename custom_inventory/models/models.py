# -*- coding: utf-8 -*-
import base64
from io import BytesIO
import xlsxwriter

from xlsxwriter import workbook

from odoo import models, fields, api, _
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import math
from odoo.exceptions import ValidationError, UserError
from odoo.fields import Many2one
from odoo.http import request


class InventoryStockIn(models.Model):
    _name = "inventory.stockin"
    _description = "Stock In"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    def _default_reference(self):
        inventoryList = self.env['inventory.stockin'].sudo().search_count([])
        return 'INVENTORY/STOCKIN/00' + str(inventoryList + 1)

    def _default_receiver(self):
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if employee:
            return employee.id

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("submit", "Submitted"),
        ("approved", "Delivery Approved"),
        ("rejected", "Rejected")
    ]

    state = fields.Selection(STATE_SELECTION, index=True, track_visibility='onchange',
                             readonly=True, required=True, copy=False, default='draft', store=True)
    name = fields.Char('Serial No', required=True, default=_default_reference)
    goods_received_date = fields.Date(string="Goods Received Date", required=True, default=fields.Date.today())
    purchaser_id = fields.Many2one('hr.employee', string="Purchased By")
    delivery_note_no = fields.Char('Delivery Note No', required=False)
    supplier_id = fields.Many2one('res.partner', string="Supplier", domain=[('supplier', '=', True)])
    receiver_id = fields.Many2one('hr.employee', string="Received By", required=True, default=_default_receiver)
    line_ids = fields.One2many('inventory.stockin.lines', 'stockin_id', string="Stock In Lines", index=True,
                               track_visibility='onchange')

    total_unit_cost = fields.Float(string="Total Unit Cost", compute='_compute_total_costs')
    total_cost = fields.Float(string="Total Cost", compute='_compute_total_costs')

    @api.depends('line_ids.unit_cost', 'line_ids.cost')
    def _compute_total_costs(self):
        for record in self:
            record.total_unit_cost = sum(line.unit_cost for line in record.line_ids)
            record.total_cost = sum(line.cost for line in record.line_ids)

    def unlink(self):
        for stockin in self:
            if stockin.state == 'approved':
                raise ValidationError(_("You cannot delete an approved stock In."))
        return super(InventoryStockIn, self).unlink()

    def button_approve(self):
        self.write({'state': 'approved'})
        for line in self.line_ids:
            line.product_id._amount_quantity()
        return True

    def button_reject(self):
        self.write({'state': 'rejected'})
        return True


    def button_submit(self):
        self.write({'state': 'submit'})
        return True


    def button_procurement(self):
        self.write({'state': 'procurement'})
        return True


    def button_reset(self):
        self.write({'state': 'draft'})
        return True



class InventoryStockInLines(models.Model):
    _name = "inventory.stockin.lines"
    _description = "Stock In Lines"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("approved", "Approved"),
        ("rejected", "Rejected")
    ]

    @api.depends('quantity', 'unit_cost')
    def total_cost_compute(self):
        for rec in self:
            rec.cost = rec.quantity * rec.unit_cost



    product_id = fields.Many2one('product.template', string="Item", required=True)
    quantity = fields.Float('Quantity', digits=(12, 2), required=True, default=1)
    unit_cost = fields.Float('Unit Cost', digits=(12, 2), required=True, default=1)
    cost = fields.Float('Total Cost', digits=(12, 2), required=True, compute="total_cost_compute")
    stockin_id = fields.Many2one('inventory.stockin', string="Stock In")
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
                             default=lambda self: self.env['uom.uom'].search([], limit=1, order='id'))
    state = fields.Selection(STATE_SELECTION, index=True, track_visibility='onchange', related='stockin_id.state',
                             store=True)


class InventoryStockOut(models.Model):
    _name = "inventory.stockout"
    _description = "Stock Out"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'


    STATE_SELECTION = [
        ("draft", "Draft"),
        ("requested", "Requested"),
        ("line_manager", "Line Manager Approve"),
        ("checked", "Procurement Checked"),
        ("issued", "AD Approved"),
        ("rejected", "Rejected")
    ]


    def _default_reference(self):
        inventoryList = self.env['inventory.stockout'].sudo().search_count([])
        return 'INVENTORY/STOCKOUT/00' + str(inventoryList + 1)


    name = fields.Char('Serial No', required=True, default=_default_reference, readonly=True)
    stock_out_date = fields.Date(string="Stock out Date", required=True, default=fields.Date.today, readonly=True)
    member_id = fields.Char(string="Member", required=True)
    issuer_id = fields.Many2one('hr.employee', string="Issued By", required=False)
    line_ids = fields.One2many('inventory.stockout.lines', 'stockout_id', string="Stock Out Lines", index=True,
                               track_visibility='onchange')
    state = fields.Selection(STATE_SELECTION, index=True, track_visibility='onchange',
                             readonly=True, required=True, copy=False, default='draft', store=True)





    def unlink(self):
        for stockout in self:
            if stockout.state == 'issued':
                raise ValidationError(_("You cannot delete an approved stockout."))
        return super(InventoryStockOut, self).unlink()


    def button_requested(self):
        self.write({'state': 'requested'})
        return True


    def button_line_manager(self, object_id):
        self.write({'state': 'line_manager'})
        return True


    def button_review(self):
        self.write({'state': 'draft'})
        return True


    def button_back_to_line(self):
        self.write({'state': 'line_manager'})
        return True


    @api.onchange('line.balance_stock', 'line.issued_quantity')
    def button_checked(self):
        for line in self.line_ids:
            if line.issued_quantity <= 0:
                raise ValidationError(_("You can't issue less than 0 goods"))
            elif line.balance_stock - line.issued_quantity < 0:
                raise ValidationError(_("There is no enough Item to issue please check stock balance"))
        self.write({'state': 'checked'})
        for line in self.line_ids:
            line.product_id._amount_quantity()
        return True


    def button_procurement_review(self):
        self.write({'state': 'line_manager'})
        return True


    def button_approve(self):
        self.write({'state': 'approved'})
        return True


    def button_issue(self):
        for line in self.line_ids:
            if line.issued_quantity < 0:
                raise ValidationError(_("One of The Lines Has an Invalid Issued Amount.Please Check"))
        self.write({'state': 'issued'})
        for line in self.line_ids:
            line.product_id._amount_quantity()
        return True


    def button_reject(self):
        self.write({'state': 'rejected'})
        return True


    def button_reset(self):
        self.write({'state': 'draft'})
        return True



class InventoryStockOutLines(models.Model):
    _name = "inventory.stockout.lines"
    _description = "Stock Out Lines"

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("requested", "Requested"),
        ("line_manager", "Line Manager Reviewed"),
        ("checked", "Procurement Checked"),
        ("issued", "Receipt Confirmed"),
        ("rejected", "Rejected")
    ]

    product_id = fields.Many2one('product.template', string="Product", required=True)
    issued_quantity = fields.Float('Issued Quantity', digits=(12, 2))
    balance_stock = fields.Float('Balance Stock', related='product_id.balance_stock')
    stockout_id = fields.Many2one(comodel_name='inventory.stockout', string="Stock Out")
    state = fields.Selection(STATE_SELECTION, index=True, track_visibility='onchange', related='stockout_id.state',
                             store=True)

class InventoryProductStockAdjustment(models.Model):
    _name = "inventory.stock.adjustment"
    _description = "Stock Inventory Adjustment"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("submit", "Submitted"),
        ("line_manager", "Line Manager Reviewed"),
        ("verify", "Procurement Verified"),
        ("approved", "Approved"),
        ("rejected", "Rejected")
    ]


    def button_submit(self):
        for line in self.stock_adjustment_line_ids:
            if line.adjustment <= 0:
                raise ValidationError(_("You should specify adjusted value amount"))
            line.state = "submit"
        self.write({'state': 'submit'})
        return True


    def button_line_manager(self):
        for line in self.stock_adjustment_line_ids:
            line.state = "line_manager"
        self.write({'state': 'line_manager'})
        return True


    def button_verify(self):
        self.write({'state': 'verify'})
        for line in self.stock_adjustment_line_ids:
            if line.adjustment <= 0:
                raise ValidationError(_("You should specify adjusted value amount"))
            line.state = "verify"

        return True


    def button_review(self):
        for line in self.stock_adjustment_line_ids:
            line.state = "draft"
        self.write({'state': 'draft'})
        return True


    def button_approve(self):
        for line in self.stock_adjustment_line_ids:
            line.state = "approved"
        for line in self.stock_adjustment_line_ids:
            line.product_id._amount_quantity()
        self.write({'state': 'approved'})
        return True


    def button_reject(self):
        for line in self.stock_adjustment_line_ids:
            line.state = "rejected"
        self.write({'state': 'rejected'})
        return True

    def _default_employee(self):
        employee = self.env['hr.employee'].sudo().search(
            [('user_id', '=', self.env.uid)], limit=1)
        if employee:
            return employee.id

    def _default_reference(self):
        inventoryList = self.env['inventory.stock.adjustment'].sudo().search_count([])
        return 'INVENTORY/ADJUSTMENT/00' + str(inventoryList + 1)

    name = fields.Char(string='Inventory Reference', default=_default_reference, required=True)
    attachment = fields.Binary(string="Attachment", attachment=True, store=True, )
    attachment_name = fields.Char('Attachment Name')
    date = fields.Date(string='Date', required=True)
    employee = fields.Many2one(comodel_name='hr.employee', string='Employee', required=True, default=_default_employee,
                               readonly=True, store=True)
    state = fields.Selection(STATE_SELECTION, index=True, track_visibility='onchange',
                             readonly=True, required=True, copy=False, default='draft', store=True)
    stock_adjustment_line_ids = fields.One2many('inventory.stock.adjustment.line', 'product_line_id',
                                                string="Stock Adjustment Lines")




class InventoryProductStockAdjustmentLines(models.Model):
    _name = "inventory.stock.adjustment.line"
    _description = "Stock Adjustment Lines"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # _order = 'id desc'

    STATE_SELECTION = [
        ("draft", "Draft"),
        ("submit", "Submitted"),
        ("line_manager", "Line Manager Reviewed"),
        ("verify", "Procurement Verified"),
        ("approved", "Approved"),
        ("rejected", "Rejected")
    ]

    state = fields.Selection(STATE_SELECTION, index=True, track_visibility='onchange',
                             readonly=True, required=True, copy=False, default='draft', store=True)
    product_id = fields.Many2one(comodel_name="product.template", string="Product")
    Actual_value = fields.Float(string="Available", related='product_id.balance_stock')
    adjustment = fields.Float(string="Adjustment")
    reason = fields.Text(string="Adjustment Reason")
    adjustment_date = fields.Date(string="Adjustment Date", compute="adjustment_data")
    product_line_id = fields.Many2one(comodel_name='inventory.stock.adjustment', string="Stock Adjustment",
                                      required=False)

    @api.depends('product_line_id.date')
    def adjustment_data(self):
        for rec in self:
            rec.adjustment_date = rec.product_line_id.date




class InventoryProductStock(models.Model):
    _inherit = "product.template"

    purchased_quantity = fields.Float('Purchased Quantity', digits=(12, 2), store=True, compute='_amount_quantity')
    issued_quantity = fields.Float('Issued Quantity', digits=(12, 2), store=True, compute='_amount_quantity')
    adjustment_quantity = fields.Float('Adjusted Quantity', digits=(12, 2), store=True, compute='_amount_quantity')
    balance_stock = fields.Float('Balance Stock', digits=(12, 2), store=True, compute='_amount_quantity')
    stockin_ids = fields.One2many('inventory.stockin.lines', 'product_id', string="Stock In Lines", index=True,
                                  track_visibility='onchange', store=True)
    department_id = fields.Many2one(comodel_name='hr.department', string="Department", required=True)
    stockout_ids = fields.One2many('inventory.stockout.lines', 'product_id', string="Stock Out Lines", index=True,
                                   track_visibility='onchange', store=True)
    stock_adjustment_ids = fields.One2many('inventory.stock.adjustment.line', 'product_id',
                                           string="Inventory Adjustment", index=True,
                                           track_visibility='onchange', store=True)
    qty_available = fields.Float('On hand', digits=(12, 2), store=True, compute='_amount_quantity')
    virtual_available = fields.Float('Forecasted', digits=(12, 2), store=True, compute='_amount_quantity')

    @api.depends('stockin_ids.quantity', 'stockout_ids.issued_quantity', 'stock_adjustment_ids.adjustment')
    def _amount_quantity(self):
        for record in self:
            stockins = 0
            for line in record.stockin_ids:
                if line.stockin_id.state == "approved":
                    stockins += line.quantity
            stockouts = 0
            for line in record.stockout_ids:
                if line.stockout_id.state == "issued":
                    stockouts += line.issued_quantity
            adjustement = 0
            for line in record.stock_adjustment_ids:
                if line.product_line_id.state == "approved":
                    adjustement += line.adjustment
            record.purchased_quantity = stockins
            record.issued_quantity = stockouts
            record.adjustment_quantity = adjustement
            record.balance_stock = stockins - stockouts - adjustement
            record.qty_available = record.balance_stock
            record.virtual_available = record.qty_available


