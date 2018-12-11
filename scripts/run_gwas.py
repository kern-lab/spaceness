from slimtools import *
import msprime as msp,pyslim,numpy as np,os,subprocess as sp
import argparse
import allel
import scipy
import random

parser = argparse.ArgumentParser(description='Run a GWAS in plink on individuals \
                                              sampled from a SLiM simulation.\
                                              Requires plink, vcftools, msprime, and pyslim.')
parser.add_argument('--infile', dest='infile',
                    help='path to simulation tree sequence.')
parser.add_argument('--outdir', dest='outdir',
                   help='Output file directory')
parser.add_argument('--plink_path', dest='plink_path',
                   help='call for plink')
parser.add_argument('--vcftools_path', dest='vcftools_path',
                   help='call for vcftools')
parser.add_argument('--nSamples', dest='nSamples', type=int,
                   help='Number of individuals to sample.')
parser.add_argument('--sampling',dest='sampling',
                   help='Type of sampling to use. Options: \
                   random (nSamples random individuals). \
                   point (nSamples individuals closest to sampling_location). \
                   pair (nSamples individuals closest to sampling_location \
                   and its reflection over the x axis)')
parser.add_argument('--mu', dest='mu',type=float,
                   help='mutation rate per base per unit time (msprime generations or SLiM time steps)')
parser.add_argument('--phenotype', dest='phenotype',
                   help='Type of phenotype to generate. \
                         options: "gaussian" (phenotypes drawn from a normal distribution); \
                                  "transform_coord" (phenotype is a transformation of the x coordinate); \
                                  "corner_bimodal" (phenotype drawn from different normal distributions \
                                  in/outside a corner of the landscape).')
parser.add_argument('--phenotype_mean', dest='phenotype_mean',type=float,
                   help='mean for gaussian phenotypes')
parser.add_argument('--phenotype_sd', dest='phenotype_sd',type=float,
                   help='standard deviation for gaussian phenotypes')
parser.add_argument('--seed', dest='seed',type=int,
                   help='Random seed for sampling individuals and adding mutations to tree sequences.')

args=parser.parse_args()

# ## debug
# args = argparse.Namespace(infile='/Users/cj/spaceness/sims/slimout/spatial/W50/coalesced/sigma_0.6544936332655427_.trees1500000.trees',
#                           outdir="/Users/cj/Desktop/",
#                           plink_path="plink",
#                           vcftools_path="vcftools",
#                           nSamples=1000,
#                           mu=0.25e-8,
#                           phenotype="random_snps",
#                           phenotype_mean=100,
#                           phenotype_sd=10,
#                           seed=123)

#sample individuals and add mutations
np.random.seed(args.seed)
simname=os.path.basename(args.infile)
ts=sample_treeseq(infile=args.infile,
                  outfile="",
                  nSamples=args.nSamples,
                  recapitate=False,
                  recombination_rate=1e-8,
                  write_to_file=False,
                  seed=args.seed)
ts=msp.mutate(ts,args.mu,random_seed=args.seed)

#get haplotypes and locations
haps=ts.genotype_matrix()
sample_inds=np.unique([ts.node(j).individual for j in ts.samples()])
locs=[[ts.individual(x).location[0],ts.individual(x).location[1]] for x in sample_inds]
np.savetxt(os.path.join(args.outdir,simname)+"_locs.txt",locs)

#run a PCA
genotype_counts=allel.HaplotypeArray(haps).to_genotypes(ploidy=2).to_allele_counts()
pca=allel.pca(genotype_counts[:,:,0])
pcfile=open(os.path.join(args.outdir,simname)+".pca","w")
for i in range(args.nSamples):
    pcfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" ")
    for j in range(10):
        pcfile.write(str(pca[0][i][j])+" ")
    pcfile.write("\n")
pcfile.close()

#write to VCF
with open(os.path.join(args.outdir,simname)+".vcf","w") as vcf_file:
    ts.write_vcf(vcf_file,2)

#convert vcf to .ped (throwing error for opening temp files when run on command line... switch to manual ped file creation?)
sp.check_output([args.vcftools_path,
                 "--vcf",
                 os.path.join(args.outdir,simname)+".vcf",
                 "--out",
                 os.path.join(args.outdir,simname),
                 "--plink"
                ])
sp.check_output(["rm",
                 os.path.join(args.outdir,simname)+".vcf"])

###create phenotypes
#normally distributed with no spatial component
if args.phenotype=="gaussian":
    phenotypes=np.random.normal(args.phenotype_mean,args.phenotype_sd,args.nSamples) #approx US height
    phenfile=open(os.path.join(args.outdir,simname)+".phenotypes","w")
    for i in range(args.nSamples):
        phenfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" "+str(phenotypes[i])+"\n")
    phenfile.close()

#x coordinate plus noise
if args.phenotype=="transform_coord":
    phenfile=open(os.path.join(args.outdir,simname)+".phenotypes","w")
    for i in range(args.nSamples):
        ind_scaling=(locs[i][0]/50)*3
        ind_phenotype=np.random.normal(args.phenotype_mean+ind_scaling*args.phenotype_sd,args.phenotype_sd,1)[0]
        phenfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" "+str(ind_phenotype)+"\n")
    phenfile.close()

#one corner has a mean 2 sd's higher than the rest of the map
if args.phenotype=="corner_bimodal":
    phenfile=open(os.path.join(args.outdir,simname)+".phenotypes","w")
    for i in range(args.nSamples):
        if locs[i][0]<20 and locs[i][1]<20:
            ind_phenotype=np.random.normal(args.phenotype_mean,args.phenotype_sd,1)[0]
        else:
            ind_phenotype=np.random.normal(args.phenotype_mean+2*args.phenotype_sd,args.phenotype_sd,1)[0]
        phenfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" "+str(ind_phenotype)+"\n")
    phenfile.close()

#individuals within 5 units of a point have their phenotype mean scaled by distance up to a factor of 2 standard deviations
if args.phenotype=="patchy":
    points = [[np.random.uniform(0,50),np.random.uniform(0,50)] for x in range(10)]
    phenfile=open(os.path.join(args.outdir,simname)+".phenotypes","w")
    for i in range(args.nSamples):
        #find distance to closest high-phenotype point
        mindist=min([scipy.spatial.distance.euclidean(locs[i],points[j]) for j in range(10)])
        if mindist > 5:
            ind_phenotype=np.random.normal(args.phenotype_mean,args.phenotype_sd,1)[0]
        else:
            ind_mean_scaling=2-(mindist/5)*2
            ind_phenotype=np.random.normal(args.phenotype_mean+args.phenotype_sd*ind_mean_scaling,args.phenotype_sd,1)[0]
        phenfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" "+str(ind_phenotype)+"\n")
    phenfile.close()

#each of 100 random SNPs adds one-tenth of a standard deviation to an individual's phenotype
if args.phenotype=="random_snps":
    phen_snps=np.random.choice([i for i in range(np.shape(haps)[0])],100) #choose 100 SNPs
    phen_allele_counts=genotype_counts[phen_snps,:,1] #count of alternate alleles
    phen_allele_counts=[sum(phen_allele_counts[:,i]) for i in range(args.nSamples)]
    phenfile=open(os.path.join(args.outdir,simname)+".phenotypes","w")
    for i in range(args.nSamples):
        ind_phenotype=args.phenotype_mean+phen_allele_counts[i]*(args.phenotype_sd/10) #each alternate allele increases phenotype by one tenth of a standard deviation
        phenfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" "+str(ind_phenotype)+"\n")
    phenfile.close()
    np.savetxt(os.path.join(args.outdir,simname)+"phenotype_snp_indices.txt",phen_snps)

#one active snp with frequency {0.1,0.2}; each alt allele adds one standard deviation
if args.phenotype=="one_snp":
    phen_snp_af=0
    while (phen_snp_af<0.1 or phen_snp_af>0.2):
        phen_snp=np.random.choice([i for i in range(np.shape(haps)[0])],1)
        phen_snp_af=sum(genotype_counts[phen_snp,:,1][0])/args.nSamples
    phenfile=open(os.path.join(args.outdir,simname)+".phenotypes","w")
    for i in range(args.nSamples):
        if genotype_counts[phen_snp,i,1]==0:
            ind_phenotype=np.random.normal(args.phenotype_mean,args.phenotype_sd,1)[0]
        if  genotype_counts[phen_snp,i,1]==1:
            ind_phenotype=np.random.normal(args.phenotype_mean+args.phenotype_sd,args.phenotype_sd,1)[0]
        if  genotype_counts[phen_snp,i,1]==2:
            ind_phenotype=np.random.normal(args.phenotype_mean+args.phenotype_sd*2,args.phenotype_sd,1)[0]
        phenfile.write("msp_"+str(i)+" "+"msp_"+str(i)+" "+str(ind_phenotype)+"\n")
    phenfile.close()

#run plink association analysis with PC coords as covariates
sp.check_output([args.plink_path,
                 "--noweb",
                 "--file",
                 os.path.join(args.outdir,simname),
                 "--pheno",
                 os.path.join(args.outdir,simname)+".phenotypes",
                 "--allow-no-sex",
                 "--out",
                 os.path.join(args.outdir,simname),
                 "--linear",
                 "--covar",
                 os.path.join(args.outdir,simname)+".pca",
                 "--hide-covar"])

#run plink without covariates
sp.check_output([args.plink_path,
                 "--noweb",
                 "--file",
                 os.path.join(args.outdir,simname),
                 "--pheno",
                 os.path.join(args.outdir,simname)+".phenotypes",
                 "--allow-no-sex",
                 "--out",
                 os.path.join(args.outdir,simname),
                 "--assoc"])

#clean up big files
sp.check_output(["rm",
                 os.path.join(args.outdir,simname)+".ped",
                 os.path.join(args.outdir,simname)+".map",
                 os.path.join(args.outdir,simname)+".nosex",
                 ])
