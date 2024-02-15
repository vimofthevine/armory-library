import CompareMetrics from '../components/compare-metrics.js';
import RunArtifacts from '../components/run-artifacts.js';
import RunDetails from '../components/run-details.js';
import RunDiff from '../components/run-diff.js';
import RunMetrics from '../components/run-metrics.js';
import RunParameters from '../components/run-parameters.js';
import RunPipeline from '../components/run-pipeline.js';
import Overview from './overview.js';
import SingleRun from './single-run.js';
import MultipleRuns from './multiple-runs.js';

export const routes = [
    { path: '/', name: 'index', component: Overview },
    {
        path: '/run/:id',
        name: 'single-run',
        component: SingleRun,
        redirect: { name: 'single-run-details' },
        props: true,
        children: [
            { path: '', name: 'single-run-details', component: RunDetails },
            { path: 'metrics', name: 'single-run-metrics', component: RunMetrics },
            { path: 'parameters', name: 'single-run-params', component: RunParameters },
            { path: 'pipeline', name: 'single-run-pipeline', component: RunPipeline },
            { path: 'artifacts', name: 'single-run-artifacts', component: RunArtifacts },
        ],
    },
    {
        path: '/compare',
        name: 'compare-runs',
        component: MultipleRuns,
        children: [
            { path: '', redirect: { name: 'compare-runs-metrics' } },
            { path: 'metrics', name: 'compare-runs-metrics', component: CompareMetrics },
            { path: 'diff', name: 'compare-runs-diff', component: RunDiff },
        ],
    },
];
