# -*- coding: utf-8 -*-
"""
Via Stitcher GUI - Enhanced wxPython dialog for via stitching configuration.
Altium-style interface with auto-preview and comprehensive options.
"""

import logging
import wx

# Get logger from parent module
logger = logging.getLogger('via_stitcher.gui')
logger.info("via_stitcher_gui module loading...")


class ViaStitcherDialog(wx.Dialog):
    """Dialog for configuring via stitching parameters."""

    # Standard copper layer names
    COPPER_LAYERS = ['F.Cu', 'In1.Cu', 'In2.Cu', 'In3.Cu', 'In4.Cu', 'In5.Cu', 'In6.Cu',
                     'In7.Cu', 'In8.Cu', 'In9.Cu', 'In10.Cu', 'B.Cu']

    def __init__(self, parent, nets=None):
        logger.info(f"ViaStitcherDialog.__init__ called, parent={parent}, nets count={len(nets) if nets else 0}")
        wx.Dialog.__init__(
            self, parent,
            id=wx.ID_ANY,
            title="Via Stitcher",
            pos=wx.DefaultPosition,
            size=wx.DefaultSize,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        logger.debug("wx.Dialog.__init__ complete")

        self.SetSizeHints(wx.Size(520, 800), wx.DefaultSize)
        self.auto_preview = True

        # Main sizer
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header
        header_panel = wx.Panel(self)
        header_panel.SetBackgroundColour(wx.Colour(50, 50, 60))
        header_sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(header_panel, wx.ID_ANY, "Via Stitcher")
        title.SetForegroundColour(wx.WHITE)
        title_font = title.GetFont()
        title_font.SetPointSize(14)
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        header_sizer.Add(title, 0, wx.ALL, 12)

        subtitle = wx.StaticText(header_panel, wx.ID_ANY, "Via stitching, zone fencing, and trace shielding")
        subtitle.SetForegroundColour(wx.Colour(180, 180, 180))
        header_sizer.Add(subtitle, 0, wx.LEFT | wx.BOTTOM, 12)

        header_panel.SetSizer(header_sizer)
        main_sizer.Add(header_panel, 0, wx.EXPAND)

        # Scrolled content area
        scroll = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 10)
        content_sizer = wx.BoxSizer(wx.VERTICAL)

        # === Net Selection Section ===
        net_box = wx.StaticBox(scroll, wx.ID_ANY, "Fence Via Net")
        net_sizer = wx.StaticBoxSizer(net_box, wx.VERTICAL)

        net_inner = wx.BoxSizer(wx.HORIZONTAL)
        self.net_choice = wx.Choice(scroll, wx.ID_ANY)
        self.net_choice.SetToolTip("Net for the stitching/fencing vias (typically GND)")
        if nets:
            for net in sorted(nets):
                if net:
                    self.net_choice.Append(net)
            gnd_idx = self.net_choice.FindString("GND")
            if gnd_idx != wx.NOT_FOUND:
                self.net_choice.SetSelection(gnd_idx)
            elif self.net_choice.GetCount() > 0:
                self.net_choice.SetSelection(0)
        net_inner.Add(self.net_choice, 1, wx.ALL | wx.EXPAND, 8)
        net_sizer.Add(net_inner, 0, wx.EXPAND)

        # Selected zones only option
        self.selected_only_cb = wx.CheckBox(scroll, wx.ID_ANY, "Selected zones only (for zone modes)")
        self.selected_only_cb.SetToolTip("Only stitch vias in currently selected zones")
        net_sizer.Add(self.selected_only_cb, 0, wx.LEFT | wx.BOTTOM, 12)

        content_sizer.Add(net_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # === Mode Section ===
        mode_box = wx.StaticBox(scroll, wx.ID_ANY, "Mode")
        mode_sizer = wx.StaticBoxSizer(mode_box, wx.VERTICAL)

        # Radio buttons for mode selection
        self.mode_fill = wx.RadioButton(scroll, wx.ID_ANY, "Fill Zone - Grid pattern inside zones", style=wx.RB_GROUP)
        self.mode_fill.SetToolTip("Fill zones with a grid pattern of vias")
        self.mode_fill.SetValue(True)
        mode_sizer.Add(self.mode_fill, 0, wx.ALL, 6)

        self.mode_fence_zone = wx.RadioButton(scroll, wx.ID_ANY, "Fence Zone - Vias around zone perimeter")
        self.mode_fence_zone.SetToolTip("Place vias around zone edges")
        mode_sizer.Add(self.mode_fence_zone, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.mode_fence_trace = wx.RadioButton(scroll, wx.ID_ANY, "Fence Trace - Shielding along selected traces")
        self.mode_fence_trace.SetToolTip("Place vias parallel to selected traces for shielding (select traces in KiCad first)")
        mode_sizer.Add(self.mode_fence_trace, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        content_sizer.Add(mode_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # === Fence Settings Section ===
        fence_box = wx.StaticBox(scroll, wx.ID_ANY, "Fence Settings")
        fence_sizer = wx.StaticBoxSizer(fence_box, wx.VERTICAL)

        fence_grid = wx.FlexGridSizer(2, 4, 8, 16)
        fence_grid.AddGrowableCol(1)
        fence_grid.AddGrowableCol(3)

        # Fence spacing
        fence_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Spacing:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.fence_spacing = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="1.0", min=0.3, max=10.0, inc=0.1)
        self.fence_spacing.SetDigits(2)
        self.fence_spacing.SetToolTip("Distance between fence vias in mm")
        fence_grid.Add(self.fence_spacing, 1, wx.EXPAND)

        # Fence offset (for trace mode)
        fence_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Offset:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.fence_offset = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.5", min=0.2, max=5.0, inc=0.1)
        self.fence_offset.SetDigits(2)
        self.fence_offset.SetToolTip("Distance from trace center to fence vias (trace mode)")
        fence_grid.Add(self.fence_offset, 1, wx.EXPAND)

        fence_sizer.Add(fence_grid, 0, wx.EXPAND | wx.ALL, 8)

        # Both sides option for trace fencing
        self.fence_both_sides_cb = wx.CheckBox(scroll, wx.ID_ANY, "Both sides of trace")
        self.fence_both_sides_cb.SetValue(True)
        self.fence_both_sides_cb.SetToolTip("Place fence vias on both sides of the trace")
        fence_sizer.Add(self.fence_both_sides_cb, 0, wx.LEFT | wx.BOTTOM, 12)

        content_sizer.Add(fence_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # === Via Properties Section ===
        via_box = wx.StaticBox(scroll, wx.ID_ANY, "Via Properties")
        via_sizer = wx.StaticBoxSizer(via_box, wx.VERTICAL)

        # Via type selection
        type_sizer = wx.BoxSizer(wx.HORIZONTAL)
        type_sizer.Add(wx.StaticText(scroll, wx.ID_ANY, "Type:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self.via_type_choice = wx.Choice(scroll, wx.ID_ANY, choices=["Through", "Blind/Buried", "Micro"])
        self.via_type_choice.SetSelection(0)
        self.via_type_choice.SetToolTip("Via type")
        type_sizer.Add(self.via_type_choice, 1, wx.ALL | wx.EXPAND, 8)
        via_sizer.Add(type_sizer, 0, wx.EXPAND)

        # Layer selection for blind/buried vias
        layer_grid = wx.FlexGridSizer(1, 4, 8, 16)
        layer_grid.AddGrowableCol(1)
        layer_grid.AddGrowableCol(3)

        self.start_layer_label = wx.StaticText(scroll, wx.ID_ANY, "Start:")
        layer_grid.Add(self.start_layer_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self.start_layer_choice = wx.Choice(scroll, wx.ID_ANY, choices=self.COPPER_LAYERS)
        self.start_layer_choice.SetSelection(0)
        layer_grid.Add(self.start_layer_choice, 1, wx.EXPAND)

        self.end_layer_label = wx.StaticText(scroll, wx.ID_ANY, "End:")
        layer_grid.Add(self.end_layer_label, 0, wx.ALIGN_CENTER_VERTICAL)
        self.end_layer_choice = wx.Choice(scroll, wx.ID_ANY, choices=self.COPPER_LAYERS)
        self.end_layer_choice.SetSelection(len(self.COPPER_LAYERS) - 1)
        layer_grid.Add(self.end_layer_choice, 1, wx.EXPAND)

        via_sizer.Add(layer_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # Via size controls
        via_grid = wx.FlexGridSizer(1, 4, 8, 16)
        via_grid.AddGrowableCol(1)
        via_grid.AddGrowableCol(3)

        via_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Diameter:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.via_size = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.6", min=0.2, max=3.0, inc=0.1)
        self.via_size.SetDigits(2)
        self.via_size.SetToolTip("Via pad diameter in mm")
        via_grid.Add(self.via_size, 1, wx.EXPAND)

        via_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Drill:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.via_drill = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.3", min=0.1, max=2.0, inc=0.1)
        self.via_drill.SetDigits(2)
        self.via_drill.SetToolTip("Via drill hole diameter in mm")
        via_grid.Add(self.via_drill, 1, wx.EXPAND)

        via_sizer.Add(via_grid, 0, wx.EXPAND | wx.ALL, 8)
        content_sizer.Add(via_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # === Grid Settings Section (for fill mode) ===
        grid_box = wx.StaticBox(scroll, wx.ID_ANY, "Grid Settings (Fill Mode)")
        grid_sizer = wx.StaticBoxSizer(grid_box, wx.VERTICAL)
        grid_grid = wx.FlexGridSizer(1, 4, 8, 16)
        grid_grid.AddGrowableCol(1)
        grid_grid.AddGrowableCol(3)

        grid_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Spacing:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.grid_spacing = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="2.0", min=0.5, max=20.0, inc=0.5)
        self.grid_spacing.SetDigits(2)
        self.grid_spacing.SetToolTip("Distance between vias in mm")
        grid_grid.Add(self.grid_spacing, 1, wx.EXPAND)

        grid_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Pattern:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.pattern_choice = wx.Choice(scroll, wx.ID_ANY, choices=["Grid", "Staggered"])
        self.pattern_choice.SetSelection(1)
        grid_grid.Add(self.pattern_choice, 1, wx.EXPAND)

        grid_sizer.Add(grid_grid, 0, wx.EXPAND | wx.ALL, 8)

        # Random offset option
        random_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.random_offset_cb = wx.CheckBox(scroll, wx.ID_ANY, "Random offset:")
        random_sizer.Add(self.random_offset_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)

        self.random_offset_max = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.2", min=0.05, max=1.0, inc=0.05)
        self.random_offset_max.SetDigits(2)
        self.random_offset_max.Enable(False)
        random_sizer.Add(self.random_offset_max, 0, wx.ALL, 8)
        random_sizer.Add(wx.StaticText(scroll, wx.ID_ANY, "mm"), 0, wx.ALIGN_CENTER_VERTICAL)

        grid_sizer.Add(random_sizer, 0, wx.EXPAND | wx.BOTTOM, 8)

        content_sizer.Add(grid_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # === Clearance Settings Section ===
        clear_box = wx.StaticBox(scroll, wx.ID_ANY, "Clearances")
        clear_sizer = wx.StaticBoxSizer(clear_box, wx.VERTICAL)
        clear_grid = wx.FlexGridSizer(1, 4, 8, 16)
        clear_grid.AddGrowableCol(1)
        clear_grid.AddGrowableCol(3)

        clear_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Copper:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.clearance = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.2", min=0.05, max=2.0, inc=0.05)
        self.clearance.SetDigits(2)
        self.clearance.SetToolTip("Minimum clearance from other copper in mm")
        clear_grid.Add(self.clearance, 1, wx.EXPAND)

        clear_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Boundary:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.boundary_clearance = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.3", min=0.1, max=5.0, inc=0.1)
        self.boundary_clearance.SetDigits(2)
        self.boundary_clearance.SetToolTip("Minimum clearance from edges in mm")
        clear_grid.Add(self.boundary_clearance, 1, wx.EXPAND)

        clear_sizer.Add(clear_grid, 0, wx.EXPAND | wx.ALL, 8)

        # Board corner radius (IPC API limitation workaround)
        corner_sizer = wx.BoxSizer(wx.HORIZONTAL)
        corner_sizer.Add(wx.StaticText(scroll, wx.ID_ANY, "Board Corner Radius:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self.board_corner_radius = wx.SpinCtrlDouble(scroll, wx.ID_ANY, value="0.0", min=0.0, max=20.0, inc=0.5)
        self.board_corner_radius.SetDigits(2)
        self.board_corner_radius.SetToolTip("Board corner radius in mm (for rounded rectangle outlines - IPC API doesn't expose this, set manually)")
        corner_sizer.Add(self.board_corner_radius, 0, wx.ALL, 8)
        corner_sizer.Add(wx.StaticText(scroll, wx.ID_ANY, "mm"), 0, wx.ALIGN_CENTER_VERTICAL)
        clear_sizer.Add(corner_sizer, 0, wx.EXPAND, 0)

        # Apology note for the manual workaround
        corner_note = wx.StaticText(scroll, wx.ID_ANY,
            "Note: KiCad's IPC API doesn't expose board corner radius yet. "
            "If your board has rounded corners, enter the radius manually. "
            "Sorry for the inconvenience - waiting on an API update!")
        corner_note.SetForegroundColour(wx.Colour(120, 120, 120))
        corner_note.Wrap(460)
        corner_note_font = corner_note.GetFont()
        corner_note_font.SetPointSize(corner_note_font.GetPointSize() - 1)
        corner_note.SetFont(corner_note_font)
        clear_sizer.Add(corner_note, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        content_sizer.Add(clear_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # === Results Section ===
        results_box = wx.StaticBox(scroll, wx.ID_ANY, "Results")
        results_sizer = wx.StaticBoxSizer(results_box, wx.VERTICAL)

        results_grid = wx.FlexGridSizer(2, 4, 4, 24)

        results_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Zones/Tracks:"), 0)
        self.zones_value = wx.StaticText(scroll, wx.ID_ANY, "-")
        self.zones_value.SetFont(self.zones_value.GetFont().Bold())
        results_grid.Add(self.zones_value, 0)

        results_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Candidates:"), 0)
        self.candidates_value = wx.StaticText(scroll, wx.ID_ANY, "-")
        self.candidates_value.SetFont(self.candidates_value.GetFont().Bold())
        results_grid.Add(self.candidates_value, 0)

        results_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Valid:"), 0)
        self.valid_value = wx.StaticText(scroll, wx.ID_ANY, "-")
        self.valid_value.SetForegroundColour(wx.Colour(0, 128, 0))
        self.valid_value.SetFont(self.valid_value.GetFont().Bold())
        results_grid.Add(self.valid_value, 0)

        results_grid.Add(wx.StaticText(scroll, wx.ID_ANY, "Rejected:"), 0)
        self.rejected_value = wx.StaticText(scroll, wx.ID_ANY, "-")
        self.rejected_value.SetForegroundColour(wx.Colour(180, 0, 0))
        self.rejected_value.SetFont(self.rejected_value.GetFont().Bold())
        results_grid.Add(self.rejected_value, 0)

        results_sizer.Add(results_grid, 0, wx.EXPAND | wx.ALL, 8)

        self.status_text = wx.StaticText(scroll, wx.ID_ANY, "Ready")
        self.status_text.SetForegroundColour(wx.Colour(80, 80, 80))
        self.status_text.Wrap(480)
        results_sizer.Add(self.status_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)

        content_sizer.Add(results_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # === Options ===
        self.auto_preview_cb = wx.CheckBox(scroll, wx.ID_ANY, "Auto-update preview on changes")
        self.auto_preview_cb.SetValue(True)
        content_sizer.Add(self.auto_preview_cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        scroll.SetSizer(content_sizer)
        main_sizer.Add(scroll, 1, wx.EXPAND)

        # === Button Bar ===
        button_panel = wx.Panel(self)
        button_panel.SetBackgroundColour(wx.Colour(240, 240, 240))
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.delete_btn = wx.Button(button_panel, wx.ID_ANY, "Delete Existing")
        button_sizer.Add(self.delete_btn, 0, wx.ALL, 8)

        self.preview_btn = wx.Button(button_panel, wx.ID_ANY, "Refresh")
        button_sizer.Add(self.preview_btn, 0, wx.ALL, 8)

        button_sizer.AddStretchSpacer()

        self.cancel_btn = wx.Button(button_panel, wx.ID_CANCEL, "Cancel")
        button_sizer.Add(self.cancel_btn, 0, wx.ALL, 8)

        self.apply_btn = wx.Button(button_panel, wx.ID_ANY, "Apply")
        self.apply_btn.SetDefault()
        button_sizer.Add(self.apply_btn, 0, wx.ALL, 8)

        button_panel.SetSizer(button_sizer)
        main_sizer.Add(button_panel, 0, wx.EXPAND)

        self.SetSizer(main_sizer)
        self.Layout()
        main_sizer.Fit(self)
        self.Centre(wx.BOTH)

        # Connect events
        self.preview_btn.Bind(wx.EVT_BUTTON, self.on_preview)
        self.apply_btn.Bind(wx.EVT_BUTTON, self.on_apply)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.delete_btn.Bind(wx.EVT_BUTTON, self.on_delete_existing)
        self.auto_preview_cb.Bind(wx.EVT_CHECKBOX, self.on_auto_preview_toggle)

        # Mode toggle events
        self.mode_fill.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)
        self.mode_fence_zone.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)
        self.mode_fence_trace.Bind(wx.EVT_RADIOBUTTON, self.on_mode_change)

        # Via type toggle
        self.via_type_choice.Bind(wx.EVT_CHOICE, self.on_via_type_change)

        # Random offset toggle
        self.random_offset_cb.Bind(wx.EVT_CHECKBOX, self.on_random_toggle)

        # Bind change events for auto-preview
        for ctrl in [self.net_choice, self.pattern_choice, self.start_layer_choice, self.end_layer_choice]:
            ctrl.Bind(wx.EVT_CHOICE, self.on_param_change)
        for ctrl in [self.selected_only_cb, self.fence_both_sides_cb]:
            ctrl.Bind(wx.EVT_CHECKBOX, self.on_param_change)
        for ctrl in [self.via_size, self.via_drill, self.grid_spacing, self.clearance,
                     self.boundary_clearance, self.fence_spacing, self.fence_offset, self.random_offset_max,
                     self.board_corner_radius]:
            ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self.on_param_change)

        # Initial UI state update
        self._update_mode_ui()
        self._update_via_type_ui()
        logger.info("ViaStitcherDialog.__init__ complete")

    def _update_mode_ui(self):
        """Update UI visibility based on mode selection."""
        is_fill = self.mode_fill.GetValue()
        is_trace = self.mode_fence_trace.GetValue()

        # Grid settings only for fill mode
        self.grid_spacing.Enable(is_fill)
        self.pattern_choice.Enable(is_fill)
        self.random_offset_cb.Enable(is_fill)
        self.random_offset_max.Enable(is_fill and self.random_offset_cb.GetValue())

        # Fence offset and both sides only for trace mode
        self.fence_offset.Enable(is_trace)
        self.fence_both_sides_cb.Enable(is_trace)

        # Selected only not applicable for trace mode
        self.selected_only_cb.Enable(not is_trace)

    def _update_via_type_ui(self):
        """Update UI visibility based on via type selection."""
        is_through = self.via_type_choice.GetSelection() == 0
        self.start_layer_label.Enable(not is_through)
        self.start_layer_choice.Enable(not is_through)
        self.end_layer_label.Enable(not is_through)
        self.end_layer_choice.Enable(not is_through)

    def get_config(self):
        """Get the current configuration from the dialog."""
        # Determine fence mode
        if self.mode_fence_zone.GetValue():
            fence_mode = 'zone'
        elif self.mode_fence_trace.GetValue():
            fence_mode = 'trace'
        else:
            fence_mode = ''  # Fill mode

        return {
            'net_name': self.net_choice.GetStringSelection(),
            'selected_only': self.selected_only_cb.GetValue(),
            'fence_mode': fence_mode,
            'via_size': self.via_size.GetValue(),
            'via_drill': self.via_drill.GetValue(),
            'via_type': self.via_type_choice.GetStringSelection(),
            'start_layer': self.start_layer_choice.GetStringSelection(),
            'end_layer': self.end_layer_choice.GetStringSelection(),
            'grid_spacing': self.grid_spacing.GetValue(),
            'clearance': self.clearance.GetValue(),
            'boundary_clearance': self.boundary_clearance.GetValue(),
            'stagger_rows': self.pattern_choice.GetSelection() == 1,
            'fence_spacing': self.fence_spacing.GetValue(),
            'fence_offset': self.fence_offset.GetValue(),
            'fence_both_sides': self.fence_both_sides_cb.GetValue(),
            'random_offset': self.random_offset_cb.GetValue(),
            'random_offset_max': self.random_offset_max.GetValue(),
            'board_corner_radius': self.board_corner_radius.GetValue(),
        }

    def update_status(self, zones=None, candidates=None, valid=None, rejected=None, message=None):
        """Update the status display."""
        if message:
            self.status_text.SetLabel(message)
            self.status_text.Wrap(480)
        if zones is not None:
            self.zones_value.SetLabel(str(zones))
        if candidates is not None:
            self.candidates_value.SetLabel(str(candidates))
        if valid is not None:
            self.valid_value.SetLabel(str(valid))
            self.apply_btn.Enable(valid > 0)
        if rejected is not None:
            self.rejected_value.SetLabel(str(rejected))
        self.Layout()

    def on_mode_change(self, event):
        """Handle mode radio button changes."""
        self._update_mode_ui()
        self.on_param_change(event)

    def on_via_type_change(self, event):
        """Handle via type selection changes."""
        self._update_via_type_ui()
        self.on_param_change(event)

    def on_random_toggle(self, event):
        """Handle random offset checkbox toggle."""
        self.random_offset_max.Enable(self.random_offset_cb.GetValue())
        self.on_param_change(event)

    def on_param_change(self, event):
        """Handle parameter changes for auto-preview."""
        if self.auto_preview_cb.GetValue():
            self.on_preview(event)
        if event:
            event.Skip()

    def on_auto_preview_toggle(self, event):
        """Handle auto-preview checkbox toggle."""
        if self.auto_preview_cb.GetValue():
            self.on_preview(event)
        event.Skip()

    # Virtual event handlers - override in derived class
    def on_preview(self, event):
        if event:
            event.Skip()

    def on_apply(self, event):
        if event:
            event.Skip()

    def on_delete_existing(self, event):
        if event:
            event.Skip()

    def on_cancel(self, event):
        self.EndModal(wx.ID_CANCEL)
