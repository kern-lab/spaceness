#!/bin/bash
for i in {1..100} 
do
	sbatch /projects/kernlab/cbattey2/spaceness/batch_scripts/runslim_spatial.srun  
	sbatch /projects/kernlab/cbattey2/spaceness/batch_scripts/runslim_random_mating.srun
done

