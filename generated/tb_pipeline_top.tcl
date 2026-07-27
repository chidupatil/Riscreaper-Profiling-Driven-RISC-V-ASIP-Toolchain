puts ">>> XSIM TCL: opening wave database"
catch {log_wave -recursive *}
puts ">>> XSIM TCL: starting run"
run -all
puts ">>> XSIM TCL: run finished"
